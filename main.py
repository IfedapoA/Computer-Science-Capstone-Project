from fastapi import FastAPI, HTTPException
import mysql.connector

app = FastAPI(title="Capstone Degree Tracking API")

# Database connection settings matching your docker-compose.yml
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "capstone",
    "database": "capstone"
}

def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

@app.get("/")
def read_root():
    return {"message": "Welcome to the Capstone API!"}

@app.get("/students")
def get_all_students():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM students;")
    students = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return {"students": students}

@app.get("/programs")
def get_all_programs():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT code, name, type, credits_required FROM programs;")
    programs = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return {"programs": programs}
