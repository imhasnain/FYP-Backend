import sys
from dotenv import load_dotenv
load_dotenv()
from database import get_connection

conn = get_connection()
c = conn.cursor()
try:
    c.execute("""
        DECLARE @ConstraintName nvarchar(200)
        SELECT @ConstraintName = Name FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('Users') AND definition LIKE '%role%'
        IF @ConstraintName IS NOT NULL
            EXEC('ALTER TABLE Users DROP CONSTRAINT ' + @ConstraintName)
    """)
    c.execute("ALTER TABLE Users ADD CONSTRAINT CHK_UserRole CHECK (role IN ('student', 'teacher', 'psychologist', 'advisor'))")

    c.execute("""
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Sections')
    BEGIN
        CREATE TABLE Sections (
            section_id INT IDENTITY(1,1) PRIMARY KEY,
            section_name VARCHAR(50) NOT NULL UNIQUE,
            advisor_id INT NOT NULL REFERENCES Users(user_id)
        )
    END
    """)

    c.execute("""
    IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Students') AND name = 'section_id')
    BEGIN
        ALTER TABLE Students ADD section_id INT NULL REFERENCES Sections(section_id)
    END
    """)

    c.execute("""
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Appointments')
    BEGIN
        CREATE TABLE Appointments (
            appointment_id INT IDENTITY(1,1) PRIMARY KEY,
            student_id INT NOT NULL REFERENCES Users(user_id),
            psychologist_id INT NOT NULL REFERENCES Users(user_id),
            session_id INT NOT NULL REFERENCES Sessions(session_id),
            status VARCHAR(20) NOT NULL DEFAULT 'Scheduled',
            created_at DATETIME NOT NULL DEFAULT GETDATE()
        )
    END
    """)

    c.execute("""
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'QuestionFeedback')
    BEGIN
        CREATE TABLE QuestionFeedback (
            feedback_id INT IDENTITY(1,1) PRIMARY KEY,
            psychologist_id INT NOT NULL REFERENCES Users(user_id),
            question_id INT NOT NULL REFERENCES Q_Questions(question_id),
            usefulness_score INT NOT NULL CHECK (usefulness_score BETWEEN 1 AND 5),
            created_at DATETIME NOT NULL DEFAULT GETDATE()
        )
    END
    """)
    
    c.execute("SELECT user_id FROM Users WHERE email='dr.smith@clinic.edu'")
    if not c.fetchone():
        c.execute("INSERT INTO Users (name, email, password, role) VALUES ('Dr. Smith', 'dr.smith@clinic.edu', '$2b$12$Z0tTqE8K/4hTfQO5OZb5.euTz0C9KzV1/0mH0VnN7pP.e4gR/c8Tq', 'psychologist')") 
        c.execute("INSERT INTO Users (name, email, password, role) VALUES ('Advisor Ali', 'ali@clinic.edu', '$2b$12$Z0tTqE8K/4hTfQO5OZb5.euTz0C9KzV1/0mH0VnN7pP.e4gR/c8Tq', 'advisor')")
    
    conn.commit()
    print('Schema updated successfully.')
    
    c.execute("SELECT user_id FROM Users WHERE email='ali@clinic.edu'")
    adv = c.fetchone()
    if adv:
        c.execute("IF NOT EXISTS(SELECT * FROM Sections WHERE section_name='BSCS 1A') INSERT INTO Sections (section_name, advisor_id) VALUES ('BSCS 1A', ?)", (adv[0],))
        c.execute("SELECT section_id FROM Sections WHERE section_name='BSCS 1A'")
        sec = c.fetchone()
        if sec:
            c.execute("UPDATE Students SET section_id=? WHERE user_id=(SELECT user_id FROM Users WHERE email='student@clinic.edu')", (sec[0],))
            conn.commit()
            print('Demo student assigned to BSCS 1A.')
            
except Exception as e:
    conn.rollback()
    print('ERROR:', e)
finally:
    conn.close()
