-- =====================================================================================
-- Capstone_Database.sql  -  SCHEMA ONLY (tables, keys, constraints, view)
--
--  * Read by migrate.py (migration 1) the first time the program starts. Do NOT mount it into Docker.
--  * Catalog, CORE curriculum and prerequisites are loaded by migrate.py from seed_data.py (migrations 2 and 3),
--    so the data lives in ONE place only.
--  * Every statement is CREATE ... IF NOT EXISTS: nothing here drops or empties a table.
--  * Contains everything the program needs:  student_core_overrides (CORE "marked satisfied"),
--    classes.department, programs.department / is_custom (outside majors and minors),
--    student_courses.grade NULL (Planned / In Progress courses have no grade yet).
-- =====================================================================================
CREATE TABLE IF NOT EXISTS catalog_years (
  id INT AUTO_INCREMENT PRIMARY KEY,
  label VARCHAR(20) NOT NULL UNIQUE,
  start_year INT NOT NULL,
  is_current BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS classes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(50) NOT NULL UNIQUE,
  name VARCHAR(200) NOT NULL,
  credits TINYINT NOT NULL DEFAULT 3,
  when_offered ENUM('Fall','Spring','Both','Not Offered') NULL,
  notes TEXT NULL,
  department VARCHAR(12) GENERATED ALWAYS AS (SUBSTRING_INDEX(code, ' ', 1)) STORED,
  INDEX idx_classes_department (department)
);

CREATE TABLE IF NOT EXISTS programs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(50) NOT NULL UNIQUE,
  name VARCHAR(150) NOT NULL,
  type ENUM('Major','Double Major','Minor') NOT NULL,
  credits_required INT NOT NULL DEFAULT 0,
  department VARCHAR(100) NULL,
  is_custom BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS prerequisites (
  course_code VARCHAR(50) NOT NULL,
  prereq_course_code VARCHAR(50) NOT NULL,
  group_no TINYINT NOT NULL DEFAULT 1,
  PRIMARY KEY (course_code, prereq_course_code),
  FOREIGN KEY (course_code) REFERENCES classes(code) ON UPDATE CASCADE ON DELETE CASCADE,
  FOREIGN KEY (prereq_course_code) REFERENCES classes(code) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS program_requirements (
  catalog_year_id INT NOT NULL,
  program_id INT NOT NULL,
  course_code VARCHAR(50) NOT NULL,
  requirement_type ENUM('Core','Elective') NOT NULL DEFAULT 'Core',
  PRIMARY KEY (catalog_year_id, program_id, course_code),
  FOREIGN KEY (catalog_year_id) REFERENCES catalog_years(id) ON DELETE CASCADE,
  FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE,
  FOREIGN KEY (course_code) REFERENCES classes(code) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS program_rules (
  catalog_year_id INT NOT NULL,
  program_id INT NOT NULL,
  electives_needed INT NOT NULL DEFAULT 0,
  PRIMARY KEY (catalog_year_id, program_id),
  FOREIGN KEY (catalog_year_id) REFERENCES catalog_years(id) ON DELETE CASCADE,
  FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE
);

-- University CORE curriculum (required of every student), versioned by catalog year.
-- A requirement is satisfied by ANY of its options. An option is a course code (PHIL 103)
-- or a pattern where a lowercase x is a wildcard (xxMO 300, xxGE 3xx, GNSCI xxx).
CREATE TABLE IF NOT EXISTS core_requirements (
  id INT AUTO_INCREMENT PRIMARY KEY,
  catalog_year_id INT NOT NULL,
  name VARCHAR(150) NOT NULL,
  take_as ENUM('Fr','So','Ju','Sr') NOT NULL DEFAULT 'Fr',
  offered ENUM('Fall','Spring','Both') NOT NULL DEFAULT 'Both',
  credits TINYINT NOT NULL DEFAULT 3,
  manual_only BOOLEAN NOT NULL DEFAULT FALSE,
  notes TEXT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  UNIQUE KEY uq_core_name (catalog_year_id, name),
  FOREIGN KEY (catalog_year_id) REFERENCES catalog_years(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS core_options (
  id INT AUTO_INCREMENT PRIMARY KEY,
  core_id INT NOT NULL,
  pattern VARCHAR(50) NOT NULL,
  UNIQUE KEY uq_core_option (core_id, pattern),
  FOREIGN KEY (core_id) REFERENCES core_requirements(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS advisors (
  id INT AUTO_INCREMENT PRIMARY KEY,
  first_name VARCHAR(100) NOT NULL,
  last_name VARCHAR(100) NOT NULL,
  email_address VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS students (
  id INT AUTO_INCREMENT PRIMARY KEY,
  first_name VARCHAR(100) NOT NULL,
  last_name VARCHAR(100) NOT NULL,
  email_address VARCHAR(100) NOT NULL UNIQUE,
  catalog_year_id INT NOT NULL,
  advisor_id INT NULL,
  FOREIGN KEY (catalog_year_id) REFERENCES catalog_years(id),
  FOREIGN KEY (advisor_id) REFERENCES advisors(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS student_programs (
  student_id INT NOT NULL,
  program_id INT NOT NULL,
  PRIMARY KEY (student_id, program_id),
  FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
  FOREIGN KEY (program_id) REFERENCES programs(id)
);

-- grade is NULL for In Progress / Planned courses.
CREATE TABLE IF NOT EXISTS student_courses (
  id INT AUTO_INCREMENT PRIMARY KEY,
  student_id INT NOT NULL,
  course_code VARCHAR(50) NOT NULL,
  term ENUM('Fall','Spring','Summer') NOT NULL,
  year INT NOT NULL,
  status ENUM('Completed','In Progress','Planned') NOT NULL,
  grade VARCHAR(3) NULL,
  is_transfer BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE KEY uq_student_course_term (student_id, course_code, term, year),
  CONSTRAINT chk_year CHECK (year BETWEEN 1990 AND 2100),
  FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
  FOREIGN KEY (course_code) REFERENCES classes(code) ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS student_core_overrides (
  student_id INT NOT NULL,
  core_id INT NOT NULL,
  course_code VARCHAR(50) NULL,
  note VARCHAR(255) NULL,
  PRIMARY KEY (student_id, core_id),
  FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
  FOREIGN KEY (core_id) REFERENCES core_requirements(id) ON DELETE CASCADE,
  FOREIGN KEY (course_code) REFERENCES classes(code) ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS substitutions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  student_id INT NOT NULL,
  required_course_code VARCHAR(50) NOT NULL,
  substitute_course_code VARCHAR(50) NOT NULL,
  note TEXT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
  FOREIGN KEY (required_course_code) REFERENCES classes(code) ON UPDATE CASCADE,
  FOREIGN KEY (substitute_course_code) REFERENCES classes(code) ON UPDATE CASCADE
);

CREATE OR REPLACE VIEW course_overlap AS
SELECT pr.catalog_year_id, pr.course_code,
       COUNT(DISTINCT pr.program_id) AS program_count,
       GROUP_CONCAT(DISTINCT p.code ORDER BY p.code SEPARATOR ', ') AS programs
FROM program_requirements pr
JOIN programs p ON p.id = pr.program_id
GROUP BY pr.catalog_year_id, pr.course_code
HAVING COUNT(DISTINCT pr.program_id) > 1;