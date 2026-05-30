from __future__ import annotations

import uuid
from datetime import datetime, date

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey,
    Integer, JSON, String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    plan = Column(String(50), nullable=False, default="starter")
    country_code = Column(String(2))
    currency = Column(String(3), default="USD")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    subjects = relationship("Subject", back_populates="tenant")


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    name = Column(String(500), nullable=False)
    industry = Column(String(100), nullable=False)
    stage = Column(String(50))
    country_code = Column(String(2))
    currency = Column(String(3), default="USD")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tenant = relationship("Tenant", back_populates="subjects")
    submissions = relationship("Submission", back_populates="subject")
    certifications = relationship("Certification", back_populates="subject")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    submitted_by = Column(UUID(as_uuid=True), nullable=True)
    data = Column(JSONB, nullable=False)        # dim_scores + metrics
    data_version = Column(Integer, default=1)
    status = Column(String(50), default="pending")
    anti_manipulation_score = Column(Float)
    anti_manipulation_flags = Column(JSONB)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    subject = relationship("Subject", back_populates="submissions")
    simulations = relationship("Simulation", back_populates="submission")


class Simulation(Base):
    __tablename__ = "simulations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    submission_id = Column(UUID(as_uuid=True), ForeignKey("submissions.id"), nullable=False)
    engine_version = Column(String(20), nullable=False, default="1.0.0")
    n_simulations = Column(Integer, default=10_000)
    seed = Column(Integer)
    p_survival = Column(Float)
    ife_score = Column(Float)
    global_score = Column(Float)
    cert_level = Column(String(20))
    score_by_dimension = Column(JSONB)
    vulnerability_map = Column(JSONB)
    stress_results = Column(JSONB)
    score_distribution = Column(JSONB)
    percentiles = Column(JSONB)
    anti_manipulation = Column(JSONB)
    cert_hash = Column(String(64))
    duration_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    submission = relationship("Submission", back_populates="simulations")
    certification = relationship("Certification", back_populates="simulation", uselist=False)


class Certification(Base):
    __tablename__ = "certifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    simulation_id = Column(UUID(as_uuid=True), ForeignKey("simulations.id"), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    level = Column(String(20), nullable=False)
    score = Column(Float, nullable=False)
    p_survival = Column(Float, nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_until = Column(Date)
    certificate_hash = Column(String(64))
    public_url = Column(String(500))
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True))
    revoke_reason = Column(Text)

    simulation = relationship("Simulation", back_populates="certification")
    subject = relationship("Subject", back_populates="certifications")


class AuditLog(Base):
    """Tabla inmutable — solo INSERT, nunca UPDATE ni DELETE."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True))
    user_id = Column(UUID(as_uuid=True))
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50))
    entity_id = Column(UUID(as_uuid=True))
    old_value = Column(JSONB)
    new_value = Column(JSONB)
    ip_address = Column(String(45))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token = Column(String(64), unique=True, nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    email = Column(String(255), nullable=True)
    company_name = Column(String(255), nullable=True)
    message = Column(Text, nullable=True)
    status = Column(String(20), default="pending")  # pending, completed, expired
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    subject = relationship("Subject", foreign_keys=[subject_id])


class Policy(Base):
    __tablename__ = "policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    
    # Identificación
    title = Column(String(500), nullable=False)
    policy_type = Column(String(50), nullable=False)  # ley, decreto, resolucion, ordenanza, acuerdo
    entity = Column(String(255), nullable=False)  # entidad que propone
    jurisdiction = Column(String(50), nullable=False)  # nacional, departamental, municipal
    country_code = Column(String(2), default="CO")
    
    # Scores por dimensión
    p1_score = Column(Float)  # Población beneficiada
    p2_score = Column(Float)  # Impacto en empleo
    p3_score = Column(Float)  # Equidad distributiva
    p4_score = Column(Float)  # Sostenibilidad fiscal
    p5_score = Column(Float)  # Viabilidad operacional
    p6_score = Column(Float)  # Riesgo de captura
    
    global_score = Column(Float)
    cert_level = Column(String(50))  # VIABLE, VIABLE_CON_OBSERVACIONES, REQUIERE_REFORMULACION, NO_VIABLE
    
    # Datos ingresados
    input_data = Column(JSONB)
    
    # Metadatos
    status = Column(String(20), default="draft")  # draft, certified, revoked
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    certified_at = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(Date, nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)