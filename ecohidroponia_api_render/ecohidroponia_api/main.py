import os
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List

import jwt
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from pwdlib import PasswordHash
from sqlalchemy import (
    create_engine, String, Integer, BigInteger, Date, DateTime, ForeignKey,
    Numeric, Text, Boolean, UniqueConstraint, Index, select
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session
from contextlib import asynccontextmanager

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Falta la variable de entorno DATABASE_URL.")

# Render puede entregar postgres:// o postgresql://. psycopg 3 usa postgresql+psycopg://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql+psycopg2://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)

SECRET_KEY = os.getenv("SECRET_KEY", "CAMBIA_ESTA_CLAVE_POR_UNA_CLAVE_LARGA_Y_ALEATORIA")
ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "1440"))
CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()]

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# -------------------- TABLAS --------------------

class Usuario(Base):
    __tablename__ = "usuarios"
    id_usuario: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    correo: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    contraseña_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    estado: Mapped[str] = mapped_column(String(20), default="activo", nullable=False)
    sistemas: Mapped[List["SistemaHidroponico"]] = relationship(back_populates="usuario")

class SistemaHidroponico(Base):
    __tablename__ = "sistemas_hidroponicos"
    id_sistema: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuarios.id_usuario", ondelete="CASCADE"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    ubicacion: Mapped[Optional[str]] = mapped_column(String(150))
    fecha_instalacion: Mapped[Optional[date]] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default="activo")
    usuario: Mapped["Usuario"] = relationship(back_populates="sistemas")
    dispositivos: Mapped[List["Dispositivo"]] = relationship(back_populates="sistema", cascade="all, delete-orphan")
    cultivos: Mapped[List["Cultivo"]] = relationship(back_populates="sistema", cascade="all, delete-orphan")

class Dispositivo(Base):
    __tablename__ = "dispositivos"
    id_dispositivo: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_sistema: Mapped[int] = mapped_column(ForeignKey("sistemas_hidroponicos.id_sistema", ondelete="CASCADE"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    identificador: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    estado: Mapped[str] = mapped_column(String(20), default="desconectado")
    ultima_conexion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sistema: Mapped["SistemaHidroponico"] = relationship(back_populates="dispositivos")
    sensores: Mapped[List["Sensor"]] = relationship(back_populates="dispositivo", cascade="all, delete-orphan")

class Cultivo(Base):
    __tablename__ = "cultivos"
    id_cultivo: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_sistema: Mapped[int] = mapped_column(ForeignKey("sistemas_hidroponicos.id_sistema", ondelete="CASCADE"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo_planta: Mapped[str] = mapped_column(String(100), nullable=False)
    fecha_siembra: Mapped[Optional[date]] = mapped_column(Date)
    fecha_estimada_cosecha: Mapped[Optional[date]] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(30), default="germinacion")
    sistema: Mapped["SistemaHidroponico"] = relationship(back_populates="cultivos")
    historial_etapas: Mapped[List["HistorialEtapa"]] = relationship(back_populates="cultivo")
    actividades: Mapped[List["ActividadCultivo"]] = relationship(back_populates="cultivo")

class EtapaCultivo(Base):
    __tablename__ = "etapas_cultivo"
    id_etapa: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(String(255))

class HistorialEtapa(Base):
    __tablename__ = "historial_etapas"
    id_historial: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_cultivo: Mapped[int] = mapped_column(ForeignKey("cultivos.id_cultivo", ondelete="CASCADE"), nullable=False, index=True)
    id_etapa: Mapped[int] = mapped_column(ForeignKey("etapas_cultivo.id_etapa"), nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, default=date.today)
    fecha_fin: Mapped[Optional[date]] = mapped_column(Date)
    observaciones: Mapped[Optional[str]] = mapped_column(String(500))
    cultivo: Mapped["Cultivo"] = relationship(back_populates="historial_etapas")

class Sensor(Base):
    __tablename__ = "sensores"
    id_sensor: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_dispositivo: Mapped[int] = mapped_column(ForeignKey("dispositivos.id_dispositivo", ondelete="CASCADE"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo_sensor: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    unidad_medida: Mapped[str] = mapped_column(String(20), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="activo")
    dispositivo: Mapped["Dispositivo"] = relationship(back_populates="sensores")
    mediciones: Mapped[List["Medicion"]] = relationship(back_populates="sensor")

class Medicion(Base):
    __tablename__ = "mediciones"
    __table_args__ = (Index("ix_mediciones_sensor_fecha", "id_sensor", "fecha_hora"),)
    id_medicion: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    id_sensor: Mapped[int] = mapped_column(ForeignKey("sensores.id_sensor", ondelete="CASCADE"), nullable=False, index=True)
    valor: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    calidad_dato: Mapped[str] = mapped_column(String(20), default="valido")
    sensor: Mapped["Sensor"] = relationship(back_populates="mediciones")

class Umbral(Base):
    __tablename__ = "umbrales"
    __table_args__ = (UniqueConstraint("tipo_sensor", "id_etapa", name="uq_umbral_tipo_etapa"),)
    id_umbral: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo_sensor: Mapped[str] = mapped_column(String(50), nullable=False)
    id_etapa: Mapped[Optional[int]] = mapped_column(ForeignKey("etapas_cultivo.id_etapa", ondelete="CASCADE"))
    valor_minimo: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    valor_maximo: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    unidad_medida: Mapped[str] = mapped_column(String(20), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="activo")

class Alerta(Base):
    __tablename__ = "alertas"
    id_alerta: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    id_sensor: Mapped[int] = mapped_column(ForeignKey("sensores.id_sensor", ondelete="CASCADE"), nullable=False, index=True)
    id_cultivo: Mapped[Optional[int]] = mapped_column(ForeignKey("cultivos.id_cultivo", ondelete="SET NULL"), index=True)
    tipo_alerta: Mapped[str] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(500), nullable=False)
    valor_detectado: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    estado: Mapped[str] = mapped_column(String(20), default="activa", index=True)

class ActividadCultivo(Base):
    __tablename__ = "actividades_cultivo"
    id_actividad: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_cultivo: Mapped[int] = mapped_column(ForeignKey("cultivos.id_cultivo", ondelete="CASCADE"), nullable=False, index=True)
    tipo_actividad: Mapped[str] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(500), nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    observaciones: Mapped[Optional[str]] = mapped_column(String(500))
    cultivo: Mapped["Cultivo"] = relationship(back_populates="actividades")

# -------------------- ESQUEMAS --------------------

class UsuarioIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=100)
    correo: EmailStr
    contraseña: str = Field(min_length=8, max_length=128)

class SistemaIn(BaseModel):
    nombre: str
    ubicacion: Optional[str] = None
    fecha_instalacion: Optional[date] = None
    estado: str = "activo"

class DispositivoIn(BaseModel):
    id_sistema: int
    nombre: str
    identificador: str
    estado: str = "desconectado"

class SensorIn(BaseModel):
    id_dispositivo: int
    nombre: str
    tipo_sensor: str
    unidad_medida: str
    estado: str = "activo"

class CultivoIn(BaseModel):
    id_sistema: int
    nombre: str
    tipo_planta: str
    fecha_siembra: Optional[date] = None
    fecha_estimada_cosecha: Optional[date] = None
    estado: str = "germinacion"

class EtapaIn(BaseModel):
    nombre: str
    descripcion: Optional[str] = None

class HistorialEtapaIn(BaseModel):
    id_cultivo: int
    id_etapa: int
    fecha_inicio: date = Field(default_factory=date.today)
    fecha_fin: Optional[date] = None
    observaciones: Optional[str] = None

class MedicionIn(BaseModel):
    id_sensor: int
    valor: float
    fecha_hora: Optional[datetime] = None
    calidad_dato: str = "valido"

class UmbralIn(BaseModel):
    tipo_sensor: str
    id_etapa: Optional[int] = None
    valor_minimo: float
    valor_maximo: float
    unidad_medida: str
    estado: str = "activo"

class AlertaIn(BaseModel):
    id_sensor: int
    id_cultivo: Optional[int] = None
    tipo_alerta: str
    descripcion: str
    valor_detectado: Optional[float] = None

class ActividadIn(BaseModel):
    id_cultivo: int
    tipo_actividad: str
    descripcion: str
    fecha_hora: Optional[datetime] = None
    observaciones: Optional[str] = None

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def crear_token(usuario_id: int):
    ahora = datetime.now(timezone.utc)
    payload = {"sub": str(usuario_id), "exp": ahora + timedelta(minutes=ACCESS_TOKEN_MINUTES)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def usuario_actual(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usuario_id = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido o vencido", headers={"WWW-Authenticate": "Bearer"})
    usuario = db.get(Usuario, usuario_id)
    if not usuario or usuario.estado != "activo":
        raise HTTPException(status_code=401, detail="Usuario no válido")
    return usuario

def comprobar_sistema(db: Session, sistema_id: int, usuario_id: int):
    sistema = db.get(SistemaHidroponico, sistema_id)
    if not sistema or sistema.id_usuario != usuario_id:
        raise HTTPException(status_code=404, detail="Sistema no encontrado")
    return sistema

def evaluar_alerta(db: Session, medicion: Medicion, sensor: Sensor):
    umbral = db.scalar(
        select(Umbral).where(
            Umbral.tipo_sensor == sensor.tipo_sensor,
            Umbral.estado == "activo",
            Umbral.id_etapa.is_(None)
        )
    )
    if not umbral:
        return
    valor = float(medicion.valor)
    if valor < float(umbral.valor_minimo):
        tipo = "valor_bajo"
        descripcion = f"{sensor.tipo_sensor} por debajo del mínimo ({valor} {sensor.unidad_medida})."
    elif valor > float(umbral.valor_maximo):
        tipo = "valor_alto"
        descripcion = f"{sensor.tipo_sensor} por encima del máximo ({valor} {sensor.unidad_medida})."
    else:
        # Cierra alertas abiertas del mismo sensor y tipo cuando vuelve al rango.
        abiertas = db.scalars(select(Alerta).where(
            Alerta.id_sensor == sensor.id_sensor,
            Alerta.estado == "activa"
        )).all()
        for a in abiertas:
            a.estado = "cerrada"
        return

    existente = db.scalar(select(Alerta).where(
        Alerta.id_sensor == sensor.id_sensor,
        Alerta.tipo_alerta == tipo,
        Alerta.estado == "activa"
    ))
    if not existente:
        db.add(Alerta(
            id_sensor=sensor.id_sensor,
            tipo_alerta=tipo,
            descripcion=descripcion,
            valor_detectado=valor,
            estado="activa"
        ))

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for nombre, descripcion in [
            ("Germinación", "Desarrollo inicial de la semilla."),
            ("Plántula", "Primeras hojas y desarrollo inicial."),
            ("Crecimiento", "Desarrollo de hojas y raíces."),
            ("Maduración", "La planta se acerca a su tamaño esperado."),
            ("Cosecha", "Etapa en la que puede recolectarse.")
        ]:
            if not db.scalar(select(EtapaCultivo).where(EtapaCultivo.nombre == nombre)):
                db.add(EtapaCultivo(nombre=nombre, descripcion=descripcion))
        db.commit()
    yield

app = FastAPI(
    title="API Ecohidroponía",
    description="API para administrar sistemas hidropónicos, cultivos, sensores, mediciones y alertas.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def inicio():
    return {"proyecto": "Ecohidroponía", "api": "activa", "documentacion": "/docs"}

@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(select(1))
        return {"estado": "saludable", "base_de_datos": "conectada"}
    except Exception:
        raise HTTPException(status_code=503, detail="No fue posible conectar con PostgreSQL")

# -------------------- AUTENTICACIÓN --------------------

@app.post("/usuarios", status_code=201)
def registrar_usuario(datos: UsuarioIn, db: Session = Depends(get_db)):
    correo = datos.correo.lower()
    if db.scalar(select(Usuario).where(Usuario.correo == correo)):
        raise HTTPException(status_code=409, detail="El correo ya está registrado")
    usuario = Usuario(
        nombre=datos.nombre,
        correo=correo,
        contraseña_hash=password_hash.hash(datos.contraseña)
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return {"id_usuario": usuario.id_usuario, "nombre": usuario.nombre, "correo": usuario.correo}

@app.post("/auth/login", response_model=LoginOut)
def iniciar_sesion(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    usuario = db.scalar(select(Usuario).where(Usuario.correo == form.username.lower()))
    if not usuario or not password_hash.verify(form.password, usuario.contraseña_hash):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")
    return {"access_token": crear_token(usuario.id_usuario), "token_type": "bearer"}

@app.get("/usuarios/me")
def mi_usuario(usuario: Usuario = Depends(usuario_actual)):
    return {"id_usuario": usuario.id_usuario, "nombre": usuario.nombre, "correo": usuario.correo}

# -------------------- SISTEMAS --------------------

@app.post("/sistemas", status_code=201)
def crear_sistema(datos: SistemaIn, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    sistema = SistemaHidroponico(id_usuario=usuario.id_usuario, **datos.model_dump())
    db.add(sistema); db.commit(); db.refresh(sistema)
    return sistema

@app.get("/sistemas")
def listar_sistemas(db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    return db.scalars(select(SistemaHidroponico).where(SistemaHidroponico.id_usuario == usuario.id_usuario)).all()

@app.get("/sistemas/{id_sistema}")
def obtener_sistema(id_sistema: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    return comprobar_sistema(db, id_sistema, usuario.id_usuario)

# -------------------- DISPOSITIVOS Y SENSORES --------------------

@app.post("/dispositivos", status_code=201)
def crear_dispositivo(datos: DispositivoIn, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    comprobar_sistema(db, datos.id_sistema, usuario.id_usuario)
    if db.scalar(select(Dispositivo).where(Dispositivo.identificador == datos.identificador)):
        raise HTTPException(status_code=409, detail="El identificador del dispositivo ya existe")
    dispositivo = Dispositivo(**datos.model_dump())
    db.add(dispositivo); db.commit(); db.refresh(dispositivo)
    return dispositivo

@app.get("/dispositivos")
def listar_dispositivos(id_sistema: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    comprobar_sistema(db, id_sistema, usuario.id_usuario)
    return db.scalars(select(Dispositivo).where(Dispositivo.id_sistema == id_sistema)).all()

@app.post("/sensores", status_code=201)
def crear_sensor(datos: SensorIn, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    dispositivo = db.get(Dispositivo, datos.id_dispositivo)
    if not dispositivo:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    comprobar_sistema(db, dispositivo.id_sistema, usuario.id_usuario)
    sensor = Sensor(**datos.model_dump())
    db.add(sensor); db.commit(); db.refresh(sensor)
    return sensor

@app.get("/sensores")
def listar_sensores(id_dispositivo: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    dispositivo = db.get(Dispositivo, id_dispositivo)
    if not dispositivo:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    comprobar_sistema(db, dispositivo.id_sistema, usuario.id_usuario)
    return db.scalars(select(Sensor).where(Sensor.id_dispositivo == id_dispositivo)).all()

# -------------------- CULTIVOS Y ETAPAS --------------------

@app.post("/cultivos", status_code=201)
def crear_cultivo(datos: CultivoIn, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    comprobar_sistema(db, datos.id_sistema, usuario.id_usuario)
    cultivo = Cultivo(**datos.model_dump())
    db.add(cultivo); db.commit(); db.refresh(cultivo)
    return cultivo

@app.get("/cultivos")
def listar_cultivos(id_sistema: Optional[int] = None, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    consulta = select(Cultivo).join(SistemaHidroponico).where(SistemaHidroponico.id_usuario == usuario.id_usuario)
    if id_sistema is not None:
        comprobar_sistema(db, id_sistema, usuario.id_usuario)
        consulta = consulta.where(Cultivo.id_sistema == id_sistema)
    return db.scalars(consulta).all()

@app.get("/cultivos/{id_cultivo}")
def obtener_cultivo(id_cultivo: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    cultivo = db.get(Cultivo, id_cultivo)
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado")
    comprobar_sistema(db, cultivo.id_sistema, usuario.id_usuario)
    return cultivo

@app.get("/etapas")
def listar_etapas(db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    return db.scalars(select(EtapaCultivo).order_by(EtapaCultivo.id_etapa)).all()

@app.post("/historial-etapas", status_code=201)
def registrar_etapa(datos: HistorialEtapaIn, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    cultivo = db.get(Cultivo, datos.id_cultivo)
    etapa = db.get(EtapaCultivo, datos.id_etapa)
    if not cultivo or not etapa:
        raise HTTPException(status_code=404, detail="Cultivo o etapa no encontrados")
    comprobar_sistema(db, cultivo.id_sistema, usuario.id_usuario)
    actual = db.scalars(select(HistorialEtapa).where(
        HistorialEtapa.id_cultivo == cultivo.id_cultivo,
        HistorialEtapa.fecha_fin.is_(None)
    )).all()
    for registro in actual:
        registro.fecha_fin = datos.fecha_inicio
    historial = HistorialEtapa(**datos.model_dump())
    cultivo.estado = etapa.nombre.lower()
    db.add(historial); db.commit(); db.refresh(historial)
    return historial

@app.get("/cultivos/{id_cultivo}/historial-etapas")
def historial_cultivo(id_cultivo: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    cultivo = db.get(Cultivo, id_cultivo)
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado")
    comprobar_sistema(db, cultivo.id_sistema, usuario.id_usuario)
    return db.scalars(select(HistorialEtapa).where(HistorialEtapa.id_cultivo == id_cultivo).order_by(HistorialEtapa.fecha_inicio)).all()

# -------------------- MEDICIONES --------------------

@app.post("/mediciones", status_code=201)
def registrar_medicion(datos: MedicionIn, db: Session = Depends(get_db)):
    # Endpoint de ingesta para el dispositivo IoT. Protegerlo adicionalmente con una API key
    # por dispositivo antes de usarlo en producción con hardware real.
    sensor = db.get(Sensor, datos.id_sensor)
    if not sensor or sensor.estado != "activo":
        raise HTTPException(status_code=404, detail="Sensor no encontrado o inactivo")
    dispositivo = db.get(Dispositivo, sensor.id_dispositivo)
    dispositivo.ultima_conexion = datetime.now(timezone.utc)
    dispositivo.estado = "en_linea"
    medicion = Medicion(
        id_sensor=datos.id_sensor,
        valor=datos.valor,
        fecha_hora=datos.fecha_hora or datetime.now(timezone.utc),
        calidad_dato=datos.calidad_dato
    )
    db.add(medicion)
    db.flush()
    evaluar_alerta(db, medicion, sensor)
    db.commit()
    db.refresh(medicion)
    return {"mensaje": "Medición registrada", "id_medicion": medicion.id_medicion, "id_sensor": medicion.id_sensor, "valor": float(medicion.valor), "fecha_hora": medicion.fecha_hora}

@app.get("/mediciones")
def listar_mediciones(
    id_sensor: int,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    limite: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_actual)
):
    sensor = db.get(Sensor, id_sensor)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor no encontrado")
    dispositivo = db.get(Dispositivo, sensor.id_dispositivo)
    comprobar_sistema(db, dispositivo.id_sistema, usuario.id_usuario)
    consulta = select(Medicion).where(Medicion.id_sensor == id_sensor)
    if desde: consulta = consulta.where(Medicion.fecha_hora >= desde)
    if hasta: consulta = consulta.where(Medicion.fecha_hora <= hasta)
    consulta = consulta.order_by(Medicion.fecha_hora.desc()).limit(limite)
    return db.scalars(consulta).all()

@app.get("/cultivos/{id_cultivo}/resumen")
def resumen_cultivo(id_cultivo: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    cultivo = db.get(Cultivo, id_cultivo)
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado")
    comprobar_sistema(db, cultivo.id_sistema, usuario.id_usuario)
    dispositivos = db.scalars(select(Dispositivo).where(Dispositivo.id_sistema == cultivo.id_sistema)).all()
    ids_dispositivos = [d.id_dispositivo for d in dispositivos]
    sensores = db.scalars(select(Sensor).where(Sensor.id_dispositivo.in_(ids_dispositivos))).all() if ids_dispositivos else []
    resultado = []
    for sensor in sensores:
        ultima = db.scalar(select(Medicion).where(Medicion.id_sensor == sensor.id_sensor).order_by(Medicion.fecha_hora.desc()).limit(1))
        resultado.append({
            "id_sensor": sensor.id_sensor,
            "nombre": sensor.nombre,
            "tipo_sensor": sensor.tipo_sensor,
            "unidad_medida": sensor.unidad_medida,
            "ultima_medicion": float(ultima.valor) if ultima else None,
            "fecha_medicion": ultima.fecha_hora if ultima else None
        })
    alertas = db.scalars(select(Alerta).where(Alerta.id_sensor.in_([s.id_sensor for s in sensores]), Alerta.estado == "activa")).all() if sensores else []
    return {
        "id_cultivo": cultivo.id_cultivo,
        "nombre": cultivo.nombre,
        "tipo_planta": cultivo.tipo_planta,
        "estado": cultivo.estado,
        "fecha_siembra": cultivo.fecha_siembra,
        "fecha_estimada_cosecha": cultivo.fecha_estimada_cosecha,
        "sensores": resultado,
        "alertas_activas": alertas
    }

# -------------------- UMBRALES Y ALERTAS --------------------

@app.post("/umbrales", status_code=201)
def crear_umbral(datos: UmbralIn, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    if datos.valor_minimo >= datos.valor_maximo:
        raise HTTPException(status_code=422, detail="El valor mínimo debe ser menor que el máximo")
    if datos.id_etapa is not None and not db.get(EtapaCultivo, datos.id_etapa):
        raise HTTPException(status_code=404, detail="Etapa no encontrada")
    umbral = Umbral(**datos.model_dump())
    db.add(umbral); db.commit(); db.refresh(umbral)
    return umbral

@app.get("/umbrales")
def listar_umbrales(db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    return db.scalars(select(Umbral).order_by(Umbral.tipo_sensor)).all()

@app.get("/alertas")
def listar_alertas(estado: Optional[str] = None, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    consulta = select(Alerta).join(Sensor).join(Dispositivo).join(SistemaHidroponico).where(SistemaHidroponico.id_usuario == usuario.id_usuario)
    if estado: consulta = consulta.where(Alerta.estado == estado)
    return db.scalars(consulta.order_by(Alerta.fecha_hora.desc())).all()

@app.patch("/alertas/{id_alerta}/cerrar")
def cerrar_alerta(id_alerta: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    alerta = db.get(Alerta, id_alerta)
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    sensor = db.get(Sensor, alerta.id_sensor)
    dispositivo = db.get(Dispositivo, sensor.id_dispositivo)
    comprobar_sistema(db, dispositivo.id_sistema, usuario.id_usuario)
    alerta.estado = "cerrada"
    db.commit()
    return {"mensaje": "Alerta cerrada", "id_alerta": id_alerta}

# -------------------- ACTIVIDADES --------------------

@app.post("/actividades", status_code=201)
def crear_actividad(datos: ActividadIn, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    cultivo = db.get(Cultivo, datos.id_cultivo)
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado")
    comprobar_sistema(db, cultivo.id_sistema, usuario.id_usuario)
    actividad = ActividadCultivo(**datos.model_dump())
    db.add(actividad); db.commit(); db.refresh(actividad)
    return actividad

@app.get("/cultivos/{id_cultivo}/actividades")
def listar_actividades(id_cultivo: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_actual)):
    cultivo = db.get(Cultivo, id_cultivo)
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado")
    comprobar_sistema(db, cultivo.id_sistema, usuario.id_usuario)
    return db.scalars(select(ActividadCultivo).where(ActividadCultivo.id_cultivo == id_cultivo).order_by(ActividadCultivo.fecha_hora.desc())).all()
