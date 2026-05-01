# ============================================================
# database/schema.sql — SQL Server DDL for VirtualClinicDB
#
# Run this script ONCE to create all tables.
# Execute in SQL Server Management Studio (SSMS):
#   1. Connect to your local SQL Server instance
#   2. Open a New Query window
#   3. Paste this entire script and press F5
#
# Or run via sqlcmd:
#   sqlcmd -S localhost -E -i schema.sql
# ============================================================

-- Create and select the database
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'VirtualClinicDB')
BEGIN
    CREATE DATABASE VirtualClinicDB;
    PRINT 'Database VirtualClinicDB created.';
END
GO

USE VirtualClinicDB;
GO

-- ============================================================
-- TABLE: Users (base user record for all roles)
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Users')
BEGIN
    CREATE TABLE Users (
        user_id     INT IDENTITY(1,1) PRIMARY KEY,
        name        VARCHAR(100)  NOT NULL,
        email       VARCHAR(100)  NOT NULL UNIQUE,
        password    VARCHAR(255)  NOT NULL,   -- plaintext password
        role        VARCHAR(20)   NOT NULL    -- 'student' | 'teacher' | 'psychologist'
                    CHECK (role IN ('student', 'teacher', 'psychologist')),
        created_at  DATETIME      NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Table Users created.';
END
GO

-- ============================================================
-- TABLE: Students (extends Users for student-specific data)
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Students')
BEGIN
    CREATE TABLE Students (
        student_id       INT IDENTITY(1,1) PRIMARY KEY,
        user_id          INT NOT NULL UNIQUE REFERENCES Users(user_id) ON DELETE CASCADE,
        cgpa_trend       FLOAT NOT NULL DEFAULT 0.0,   -- negative = declining GPA
        attendance_drop  FLOAT NOT NULL DEFAULT 0.0    -- positive = more absences
    );
    PRINT 'Table Students created.';
END
GO

-- ============================================================
-- TABLE: Teachers (extends Users for teacher-specific data)
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Teachers')
BEGIN
    CREATE TABLE Teachers (
        teacher_id   INT IDENTITY(1,1) PRIMARY KEY,
        user_id      INT NOT NULL UNIQUE REFERENCES Users(user_id) ON DELETE CASCADE,
        workload_hrs FLOAT NOT NULL DEFAULT 0.0,
        class_count  INT   NOT NULL DEFAULT 0
    );
    PRINT 'Table Teachers created.';
END
GO

-- ============================================================
-- TABLE: Sessions
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Sessions')
BEGIN
    CREATE TABLE Sessions (
        session_id  INT IDENTITY(1,1) PRIMARY KEY,
        user_id     INT NOT NULL REFERENCES Users(user_id),
        start_time  DATETIME NOT NULL,
        end_time    DATETIME NULL,
        status      VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'completed'))
    );
    PRINT 'Table Sessions created.';
END
GO

-- ============================================================
-- TABLE: Q_Stages
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Q_Stages')
BEGIN
    CREATE TABLE Q_Stages (
        stage_id      INT IDENTITY(1,1) PRIMARY KEY,
        stage_number  INT           NOT NULL UNIQUE CHECK (stage_number BETWEEN 1 AND 5),
        stage_name    VARCHAR(100)  NOT NULL,
        target_role   VARCHAR(20)   NOT NULL  -- 'student' | 'teacher' | 'both'
                      CHECK (target_role IN ('student', 'teacher', 'both')),
        threshold     FLOAT         NOT NULL  -- minimum passing score
    );
    PRINT 'Table Q_Stages created.';
END
GO

-- ============================================================
-- TABLE: Q_Questions
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Q_Questions')
BEGIN
    CREATE TABLE Q_Questions (
        question_id   INT IDENTITY(1,1) PRIMARY KEY,
        stage_id      INT           NOT NULL REFERENCES Q_Stages(stage_id),
        question_text VARCHAR(500)  NOT NULL,
        weight        FLOAT         NOT NULL DEFAULT 1.0
    );
    PRINT 'Table Q_Questions created.';
END
GO

-- ============================================================
-- TABLE: Q_Responses
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Q_Responses')
BEGIN
    CREATE TABLE Q_Responses (
        response_id     INT IDENTITY(1,1) PRIMARY KEY,
        session_id      INT           NOT NULL REFERENCES Sessions(session_id),
        question_id     INT           NOT NULL REFERENCES Q_Questions(question_id),
        stage_number    INT           NOT NULL,
        response_choice VARCHAR(50)   NOT NULL,
        cal_score       FLOAT         NOT NULL,
        timestamp       DATETIME      NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Table Q_Responses created.';
END
GO

-- ============================================================
-- TABLE: SensorData
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'SensorData')
BEGIN
    CREATE TABLE SensorData (
        sensor_id           INT IDENTITY(1,1) PRIMARY KEY,
        session_id          INT          NOT NULL REFERENCES Sessions(session_id),
        eeg_value           FLOAT        NULL,
        ppg_value           FLOAT        NULL,
        bp_systolic         INT          NULL,
        bp_diastolic        INT          NULL,
        pulse_rate          INT          NULL,
        emotion             VARCHAR(50)  NULL,
        emotion_confidence  FLOAT        NULL,
        data_type           VARCHAR(20)  NOT NULL
                            CHECK (data_type IN ('eeg', 'ppg', 'bp', 'emotion')),
        recorded_at         DATETIME     NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Table SensorData created.';
END
GO

-- ============================================================
-- TABLE: FacialEmotions
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'FacialEmotions')
BEGIN
    CREATE TABLE FacialEmotions (
        emotion_id        INT IDENTITY(1,1) PRIMARY KEY,
        session_id        INT          NOT NULL REFERENCES Sessions(session_id),
        dominant_emotion  VARCHAR(50)  NOT NULL,
        happy             FLOAT        NOT NULL DEFAULT 0.0,
        sad               FLOAT        NOT NULL DEFAULT 0.0,
        angry             FLOAT        NOT NULL DEFAULT 0.0,
        fear              FLOAT        NOT NULL DEFAULT 0.0,
        surprise          FLOAT        NOT NULL DEFAULT 0.0,
        disgust           FLOAT        NOT NULL DEFAULT 0.0,
        neutral           FLOAT        NOT NULL DEFAULT 0.0,
        captured_at       DATETIME     NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Table FacialEmotions created.';
END
GO

-- ============================================================
-- TABLE: MH_Results
-- ============================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'MH_Results')
BEGIN
    CREATE TABLE MH_Results (
        result_id         INT IDENTITY(1,1) PRIMARY KEY,
        session_id        INT          NOT NULL UNIQUE REFERENCES Sessions(session_id),
        user_id           INT          NOT NULL REFERENCES Users(user_id),
        emotional_score   FLOAT        NOT NULL DEFAULT 0.0,
        functional_score  FLOAT        NOT NULL DEFAULT 0.0,
        context_score     FLOAT        NOT NULL DEFAULT 0.0,
        isolation_score   FLOAT        NOT NULL DEFAULT 0.0,
        critical_score    FLOAT        NOT NULL DEFAULT 0.0,
        eeg_avg           FLOAT        NULL,
        avg_pulse         FLOAT        NULL,
        avg_bp_systolic   FLOAT        NULL,
        dominant_emotion  VARCHAR(50)  NULL,
        final_score       FLOAT        NOT NULL,
        risk_class        VARCHAR(50)  NOT NULL
                          CHECK (risk_class IN (
                              'Healthy', 'Mild Stress',
                              'Moderate Risk', 'High Risk', 'Critical Risk'
                          )),
        calculated_at     DATETIME     NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Table MH_Results created.';
END
GO

-- ============================================================
-- SEED DATA: Q_Stages (5 stages of the questionnaire)
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM Q_Stages)
BEGIN
    INSERT INTO Q_Stages (stage_number, stage_name, target_role, threshold) VALUES
    (1, 'Emotional Wellbeing Assessment',   'both',    2.0),
    (2, 'Functional Impairment Screening',  'both',    1.5),
    (3, 'Contextual Stressor Evaluation',   'both',    1.0),
    (4, 'Social Isolation & Support Check', 'both',    1.5),
    (5, 'Critical Risk Indicators',         'both',    0.5);
    PRINT 'Q_Stages seed data inserted.';
END
GO

-- ============================================================
-- SEED DATA: Q_Questions (sample questions per stage)
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM Q_Questions)
BEGIN
    -- Stage 1: Emotional Wellbeing (stage_id = 1)
    INSERT INTO Q_Questions (stage_id, question_text, weight) VALUES
    (1, 'Over the last two weeks, how often have you felt down, depressed, or hopeless?', 1.0),
    (1, 'How often have you had little interest or pleasure in doing things?', 1.0),
    (1, 'How often do you feel nervous, anxious, or on edge?', 1.0),
    (1, 'How often do you feel unable to control worrying?', 1.0),

    -- Stage 2: Functional Impairment (stage_id = 2)
    (2, 'How often have these feelings made it difficult to do your work or studies?', 1.0),
    (2, 'How often have they affected your ability to take care of daily responsibilities?', 1.0),
    (2, 'How much have these problems affected your sleep quality?', 1.0),

    -- Stage 3: Contextual Stressors (stage_id = 3)
    (3, 'Are you currently under significant academic or work pressure?', 1.0),
    (3, 'Have you experienced any major life events recently (loss, conflict, etc.)?', 1.0),
    (3, 'Do you feel your current environment is stressful or unsupportive?', 1.0),

    -- Stage 4: Social Isolation (stage_id = 4)
    (4, 'How often do you feel lonely or isolated from others?', 1.0),
    (4, 'Do you have people you can turn to when feeling stressed?', 1.0),
    (4, 'How often do you withdraw from social activities you used to enjoy?', 1.0),

    -- Stage 5: Critical Indicators (stage_id = 5)
    (5, 'Have you had thoughts that you would be better off dead or of hurting yourself?', 2.0),
    (5, 'Have you had thoughts of harming others?', 2.0),
    (5, 'Do you feel completely hopeless about the future?', 1.5);

    PRINT 'Q_Questions seed data inserted.';
END
GO

-- ============================================================
-- SEED DATA: Pre-registered Users
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM Users WHERE email = 'student@clinic.edu')
BEGIN
    -- Base User (Student)
    -- password is 'password123' (plaintext)
    INSERT INTO Users (name, email, password, role)
    VALUES ('Demo Student', 'student@clinic.edu', 'password123', 'student');
    
    DECLARE @student_user_id INT = SCOPE_IDENTITY();
    
    -- Extended Student Data
    INSERT INTO Students (user_id, cgpa_trend, attendance_drop)
    VALUES (@student_user_id, -0.2, 5.0);
    
    PRINT 'Student seed data inserted.';
END
GO

IF NOT EXISTS (SELECT 1 FROM Users WHERE email = 'teacher@clinic.edu')
BEGIN
    -- Base User (Teacher)
    -- password is 'password123' (plaintext)
    INSERT INTO Users (name, email, password, role)
    VALUES ('Demo Teacher', 'teacher@clinic.edu', 'password123', 'teacher');
    
    DECLARE @teacher_user_id INT = SCOPE_IDENTITY();
    
    -- Extended Teacher Data
    INSERT INTO Teachers (user_id, workload_hrs, class_count)
    VALUES (@teacher_user_id, 24.5, 4);
    
    PRINT 'Teacher seed data inserted.';
END
GO

PRINT '=== VirtualClinicDB schema created successfully ===';
GO

