/*
	Capstone Poject prototype
*/

CREATE SCHEMA IF NOT EXISTS capstone;
USE capstone;
DROP TABLE IF EXISTS stuff;

#Student
CREATE TABLE IF NOT EXISTS students (
	id INTEGER AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) UNIQUE NOT NULL,
    email_address VARCHAR(100)
);

#Advisor
CREATE TABLE IF NOT EXISTS advisors (
	email_address VARCHAR(100) PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) UNIQUE NOT NULL
);

#Classes
CREATE TABLE IF NOT EXISTS classes (
	id INTEGER AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    when_offered ENUM('Fall', 'Spring', 'Both', 'Not Offered'),
    notes TEXT
);

#Programs
CREATE TABLE IF NOT EXISTS programs (
	id INTEGER AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    type ENUM('Major', 'Double Major', 'Minor') NOT NULL,
    credits_required INTEGER NOT NULL
    #total_graduation_credits INTEGER DEFAULT 120
);

#Prerequisites
CREATE TABLE IF NOT EXISTS prerequisites (
	course_code VARCHAR(50) NOT NULL,
    prereq_course_code VARCHAR(50) NOT NULL,
    PRIMARY KEY (course_code, prereq_course_code),
    FOREIGN KEY (course_code) REFERENCES classes(code),
    FOREIGN KEY (prereq_course_code) REFERENCES classes(code)
);

/*
CREATE TABLE IF NOT EXISTS prerequisites (
	course_code VARCHAR(50) NOT NULL,
    prereq_course_code VARCHAR(50) NOT NULL,
    PRIMARY KEY (course_code, prereq_course_code),
    FOREIGN KEY (course_code) REFERENCES classes(code) ON DELETE CASCADE,
    FOREIGN KEY (prereq_course_code) REFERENCES classes(code) ON DELETE CASCADE
);
*/

#Program Requirements
CREATE TABLE IF NOT EXISTS program_requirements (
    program_id INTEGER NOT NULL,
    course_code VARCHAR(50),
    requirement_type ENUM('Core', 'Elective') DEFAULT 'Core',
    PRIMARY KEY (program_id, course_code),
    FOREIGN KEY (program_id) REFERENCES programs(id),
    FOREIGN KEY (course_code) REFERENCES classes(code)
);

CREATE TABLE IF NOT EXISTS users (
	email_address VARCHAR(50) PRIMARY KEY,
    role ENUM('Advisor', 'Student'),
    FOREIGN KEY (email_address) REFERENCES students(email_address),
    FOREIGN KEY (email_address) REFERENCES advisors(email_address)
);

SELECT * FROM students;

DROP TABLE IF EXISTS students;

SELECT * FROM advisors;

DROP TABLE IF EXISTS advisors;

SELECT * FROM classes;

DROP TABLE IF EXISTS classes;

SELECT * FROM programs;

DROP TABLE IF EXISTS programs;

SELECT * FROM prerequisites;

DROP TABLE IF EXISTS prerequisites;

SELECT * FROM program_requirements;

DROP TABLE IF EXISTS program_requirements;

INSERT INTO programs (code, name, type, credits_required) VALUES
('CS', 'Computer Science', 'Major', 43),
('Cyber', 'Cybersecurity', 'Major', 48),
('Data', 'Data Science', 'Major', 49),
('Math', 'Mathematics', 'Major', 41),
('Cyber&CS', 'Computer Science & Cybersecurity', 'Double Major', 64),
('Math&CS', 'Mathematics & Computer Science', 'Double Major', 69),
('Cyber&Data', 'Cybersecurity & Data Science', 'Double Major', 67),
('CS&Data', 'Computer Science & Data Science', 'Double Major', 65),
('Math&Data', 'Mathematics & Data Science', 'Double Major', 65),
('CS-M', 'Computer Science Minor', 'Minor', 18),
('Cyber-M', 'Cybersecurity Minor', 'Minor', 18),
('Math-M', 'Mathematics Minor', 'Minor', 19),
('Data-M', 'Data Science Minor', 'Minor', 18);

#Insert all the Computer Science classes
INSERT INTO classes(code, name, when_offered, notes) VALUES
('CMSCI 101', 'Computer Technology', 'Not Offered', "Not offered since the late 2010s"),
('CMSCI 115', 'Computer Games and Gaming', 'Not Offered', "Not offered since the late 2010s"),
('CMSCI 119', 'Intro to Artificial Intelligence', NULL, "New course, never been offered"),
('CMSCI 120', 'Introduction to Computer Science I', 'Both', NULL),
('CMSCI 125', 'Introduction to Computer Science II', 'Both', NULL),
('CMSCI 254', 'Data Structures and Algorithms', 'Fall', NULL),
('CMSCI 256', 'Principles of Software Development', 'Spring', NULL),
('CMSCI 277', 'Computer Systems', 'Fall', NULL),
('CMSCI 305', 'Mobile App Development', NULL, "New course, never been offered"),
('CMSCI 349', 'Software Engineering', 'Fall', NULL),
('CMSCI 355', 'Network Systems and Design', 'Fall', NULL),
('CMSCI 356', 'Operating Systems', 'Spring', NULL),
('CMSCI 358', 'Computer Security I', 'Fall', NULL),
('CMSCI 359', 'Database Management Systems', 'Spring', NULL),
('CMSCI 368', 'Computer Security II', 'Spring', "Spring of odd years"),
('CMSCI 369', 'Database Implementation', NULL, "Never been offered"),
('CMSCI 394', 'Computer Graphics', 'Spring', "On a rotating basis"),
('CMSCI 398', 'Independent Study', NULL, NULL),
('CMSCI 442', 'Principles of Programming Languages', 'Fall', "Fall of odd years"),
('CMSCI 449', 'AI Theory & Implementation', 'Spring', "Spring of even years"),
('CMSCI 452', 'Compiler Design', 'Fall', "Fall of even years"),
('CMSCI 453', 'Algorithms', 'Spring', NULL),
('CMSCI 474', 'Computer Science Capstone I', 'Fall', NULL),
('CMSCI 475', 'Computer Science Capstone II', 'Spring', NULL),
('CMSCI 485', 'Theory of Computation', 'Fall', NULL),
('CMSCI 492', 'Practicum', NULL, NULL),
('CMSCI 493', 'Practicum', NULL, NULL),
('CMSCI 499', 'Special Topics in Computer Science', NULL, NULL);

#Insert all the Cybersecurity classes
INSERT INTO classes(code, name, when_offered, notes) VALUES
('CYBER 100', 'Foundations of Cybersecurity', NULL, NULL),
('CYBER 260', 'Networking Administration', 'Spring', NULL),
('CYBER 261', 'Unix and Windows Operating Systems', 'Fall', NULL),
('CYBER 283', 'Critical Infrastructure Security', NULL, "On a rotating basis"),
('CYBER 301', 'Secure Systems Design and Risk Management', 'Fall', NULL),
('CYBER 310', 'Systems Operations Management', 'Spring', NULL),
('CYBER 354', 'Cloud Security', NULL, "On a rotating basis"),
('CYBER 357', 'Network Security', 'Spring', NULL),
('CYBER 365', 'Penetration Testing and Ethical Hacking', NULL, "On a rotating basis"),
('CYBER 398', 'Independent Study', NULL, NULL),
('CYBER 400', 'Cybersecurity Capstone', 'Both', NULL),
('CYBER 492', 'Practicum', NULL, NULL),
('CYBER 493', 'Practicum', NULL, NULL),
('CYBER 499', 'Special topics in Cybersecurity', NULL, NULL);

#Insert the Data classes
INSERT INTO classes(code, name, when_offered, notes) VALUES
('DATA 200', 'Introduction to Data Science', 'Both', NULL),
('DATA 201', 'Special Topics in Data Science', 'Both', NULL),
('DATA 210', 'Exploratory Data Analysis', 'Spring', NULL),
('DATA 220', 'Machine Learning Models', 'Fall', NULL),
('DATA 320', 'Distributed Data Systems', 'Spring', "Spring of odd years"),
('DATA 330', 'Data Wrangling', 'Fall', "Fall of odd years"),
('DATA 340', 'Advanced Data Visualization', 'Spring', "Spring of even years"),
('DATA 350', 'Natural Language Processing', 'Fall', "Fall of even years"),
('DATA 410', 'Advanced Machine Learning', NULL, NULL),
('DATA 420', 'High Performance Computing', NULL, NULL),
('DATA 430', 'Network Science', NULL, NULL),
('DATA 475', 'Data Science Capstone', 'Spring', NULL),
('DATA 492', 'Data Science Practicum', NULL, NULL),
('DATA 493', 'Data Science Practicum', NULL, NULL);

#Insert the Math classes
INSERT INTO classes(code, name, when_offered, notes) VALUES
('MATH 105', 'Elementary Statistics', 'Both', NULL),
('MATH 108', 'Concepts of Mathematics for Teachers I', 'Fall', NULL),
('MATH 109', 'Concepts of Mathematics for Teachers II', 'Spring', NULL),
('MATH 114', 'Precalculus Mathematics', 'Fall', NULL),
('MATH 211', 'Mathematical Thinking', 'Both', NULL),
('MATH 228', 'Discrete Mathematics', 'Both', NULL),
('MATH 247', 'Calculus I', 'Both', NULL),
('MATH 248', 'Calculus II', 'Spring', NULL),
('MATH 249', 'Calculus III', 'Fall', NULL),
('MATH 332', 'Graph Theory', 'Fall', "On a rotating basis, typically fall of even years"),
('MATH 336', 'Elementary Number Theory', 'Fall', "On a rotating basis, typically fall of odd years"),
('MATH 364', 'Linear Algebra', 'Spring', NULL),
('MATH 377', 'Foundations of Geometry', 'Spring', "Spring of odd years"),
('MATH 384', 'Differential Equations', 'Spring', "Spring of odd years"),
('MATH 387', 'Probability', 'Spring', "On a rotating basis, typically spring of odd years"),
('MATH 388', 'Operations Research', 'Fall', "On a rotating basis, typically fall of seven years"),
('MATH 389', 'Numerical Methods', 'Fall', "On a rotating basis, typically fall of odd years. Same as CMSCI 389."),
('MATH 390', 'Mathematical Statistics', 'Not offered', NULL),
('MATH 398', 'Independent Study', NULL, NULL),
('MATH 447', 'Intoduction to Real Analysis', NULL, NULL),
('MATH 457', 'Introduction to Complex Analysis', 'Not offered', NULL),
('MATH 464', 'Advanced Linear Algebra', 'Not offered', NULL),
('MATH 468', 'Algebraic Structures', 'Spring', "Spring of even years"),
('MATH 472', 'Topology', 'Not offered', NULL),
('MATH 488', 'Stochastic Processes', 'Not offered', NULL),
('MATH 489', 'Modeling and Simulation', 'Not offered', "Same as CMSCI 489"),
('MATH 492', 'Practicum', NULL, NULL),
('MATH 493', 'Practicum', NULL, NULL),
('MATH 495', 'Seminar I', 'Spring', NULL),
('MATH 496', 'Seminar II', 'Spring', NULL),
('MATH 497', 'Undergraduate Research in Mathematics', NULL, NULL),
('MATH 499', 'Special Topics in Mathematics', NULL, NULL);

#Insert prerequisites for the CMSI classes
INSERT INTO prerequisites(course_code, prereq_course_code) VALUES
('CMSCI 125', 'CMSCI 120'),
('CMSCI 254', 'CMSCI 125'),
('CMSCI 256', 'CMSCI 125'),
('CMSCI 277', 'CMSCI 120'),
('CMSCI 305', 'CMSCI 125'),
('CMSCI 349', 'CMSCI 254'),
('CMSCI 355', 'CMSCI 125'),
('CMSCI 356', 'CMSCI 125'),
('CMSCI 356', 'CMSCI 277'),
('CMSCI 358', 'CMSCI 125'),
('CMSCI 359', 'CMSCI 125'),
('CMSCI 368', 'CMSCI 358'),
('CMSCI 369', 'CMSCI 359'),
('CMSCI 394', 'CMSCI 125'),
('CMSCI 442', 'CMSCI 254'),
('CMSCI 449', 'CMSCI 254'),
('CMSCI 452', 'CMSCI 254'),
('CMSCI 453', 'CMSCI 254'),
('CMSCI 453', 'MATH 228'),
('CMSCI 474', 'CMSCI 254'),
('CMSCI 475', 'CMSCI 474'),
('CMSCI 485', 'CMSCI 254'),
('CMSCI 485', 'MATH 228');

#Insert prerequisites for the CYBER classes
INSERT INTO prerequisites(course_code, prereq_course_code) VALUES
('CYBER 260', 'CMSCI 120'),
('CYBER 261', 'CMSCI 125'),
('CYBER 283', 'CMSCI 120'),
('CYBER 301', 'CMSCI 125'),
('CYBER 310', 'CMSCI 125'),
('CYBER 354', 'CYBER 260'),
('CYBER 354', 'CMSCI 355'),
('CYBER 357', 'CMSCI 355'),
('CYBER 365', 'CYBER 260');

#Insert prerequisites for the DATA classes
INSERT INTO prerequisites(course_code, prereq_course_code) VALUES
('DATA 201', 'DATA 200'),
('DATA 210', 'DATA 200'),
('DATA 220', 'DATA 210'),
('DATA 320', 'DATA 200'),
('DATA 330', 'DATA 200'),
('DATA 340', 'DATA 200'),
('DATA 350', 'DATA 200'),
('DATA 320', 'CMSCI 125'),
('DATA 330', 'CMSCI 125'),
('DATA 340', 'CMSCI 125'),
('DATA 350', 'CMSCI 125'),
('DATA 410', 'DATA 220'),
('DATA 420', 'DATA 220'),
('DATA 430', 'DATA 220');

#Insert prerequisites for the DATA classes
INSERT INTO prerequisites(course_code, prereq_course_code) VALUES
('MATH 247', 'MATH 114'),
('MATH 248', 'MATH 247'),
('MATH 249', 'MATH 248'),
('MATH 332', 'MATH 228'),
('MATH 336', 'MATH 228'),
('MATH 336', 'MATH 247'),
('MATH 364', 'MATH 228'),
('MATH 364', 'MATH 247'),
('MATH 377', 'MATH 228'),
('MATH 384', 'MATH 248'),
('MATH 387', 'MATH 228'),
('MATH 387', 'MATH 248'),
('MATH 388', 'MATH 228'),
('MATH 388', 'MATH 247'),
('MATH 389', 'MATH 247'),
('MATH 389', 'CMSCI 120'),
('MATH 390', 'MATH 387'),
('MATH 447', 'MATH 248'),
('MATH 457', 'MATH 249'),
('MATH 464', 'MATH 364'),
('MATH 468', 'MATH 228'),
('MATH 468', 'MATH 248'),
('MATH 472', 'MATH 228'),
('MATH 472', 'MATH 248'),
('MATH 488', 'MATH 387'),
('MATH 489', 'MATH 248');
