import os
import csv
import io
import logging
from typing import Optional, List

from dotenv import load_dotenv
load_dotenv()

from azure.storage.blob import BlobSasPermissions, generate_blob_sas, BlobServiceClient
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends, Header, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# === CONFIG ===
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_CONTAINER = "todo-exports"
API_KEY = os.getenv("API_KEY", "mysecretkey")

# === SETUP ===
app = FastAPI()
Base = declarative_base()
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# === MODELS ===
class Todo(Base):
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
    due_date = Column(DateTime)
    created = Column(DateTime, server_default=func.now())
    completed = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

# === SCHEMAS ===
class TodoBase(BaseModel):
    title: str
    description: str
    due_date: datetime

class TodoCreate(TodoBase): 
    pass

class TodoUpdate(TodoBase):
    completed: bool

class TodoOut(TodoBase):
    id: int
    created: datetime
    completed: bool

    class Config:
        orm_mode = True

# === AUTH & LOGGING ===
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

def check_auth(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")

# === AZURE UPLOAD ===
def upload_to_azure(filename: str, content: str) -> str:
    blob_service = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service.get_container_client(AZURE_CONTAINER)

    # Create container if it doesn't exist
    if not container_client.exists():
        container_client.create_container()

    blob_client = container_client.get_blob_client(filename)
    blob_client.upload_blob(content, overwrite=True)

    # Generate SAS token
    sas_token = generate_blob_sas(
        account_name=blob_client.account_name,
        container_name=blob_client.container_name,
        blob_name=blob_client.blob_name,
        account_key=blob_service.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(minutes=15)  # Link expires in 15 minutes
    )

    # Construct full URL with SAS
    sas_url = f"https://{blob_client.account_name}.blob.core.windows.net/{blob_client.container_name}/{blob_client.blob_name}?{sas_token}"
    return sas_url

# === ROUTES ===
@app.post("/todos", dependencies=[Depends(check_auth)], response_model=TodoOut)
def create_todo(todo: TodoCreate, db: Session = Depends(get_db)):
    db_todo = Todo(**todo.dict())
    db.add(db_todo)
    db.commit()
    db.refresh(db_todo)
    return db_todo

@app.get("/todos", dependencies=[Depends(check_auth)], response_model=List[TodoOut])
def read_todos(completed: Optional[bool] = None, db: Session = Depends(get_db)):
    if completed is None:
        return db.query(Todo).all()
    return db.query(Todo).filter(Todo.completed == completed).all()

@app.put("/todos/{todo_id}", dependencies=[Depends(check_auth)], response_model=TodoOut)
def update_todo(todo_id: int, todo: TodoUpdate, db: Session = Depends(get_db)):
    db_todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not db_todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    for key, value in todo.dict().items():
        setattr(db_todo, key, value)
    db.commit()
    db.refresh(db_todo)
    return db_todo

@app.delete("/todos/{todo_id}", dependencies=[Depends(check_auth)])
def delete_todo(todo_id: int, db: Session = Depends(get_db)):
    db_todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not db_todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    db.delete(db_todo)
    db.commit()
    return {"detail": "Deleted"}

@app.get("/export", dependencies=[Depends(check_auth)])
def export_todos(db: Session = Depends(get_db), x_api_key: str = Header(...)):
    todos = db.query(Todo).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["ID", "Title", "Description", "Due Date", "Created", "Completed"])
    for t in todos:
        writer.writerow([t.id, t.title, t.description, t.due_date, t.created, t.completed])
    filename = f"todos_{datetime.utcnow().isoformat()}.csv"
    url = upload_to_azure(filename, buffer.getvalue())
    logging.info(f"Export by {x_api_key} at {datetime.utcnow()}")
    return {"url": url}

@app.get("/")
def read_root():
    return {"message": "Todo API is running"}
