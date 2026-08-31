DROP TABLE IF EXISTS `employees`;
CREATE TABLE `employees` (
  `employee_id`   VARCHAR(32)   NOT NULL,
  `name`          VARCHAR(64)   NOT NULL,
  `department`    VARCHAR(64)   NOT NULL,
  `position`      VARCHAR(64)   DEFAULT '',
  `level`         VARCHAR(32)   DEFAULT '',
  `salary`        DECIMAL(12,2) DEFAULT 0.00,
  `hire_date`     DATE          DEFAULT NULL,
  `status`        VARCHAR(16)   DEFAULT 'active',
  `gender`        VARCHAR(16)   DEFAULT '',
  `age`           INT           DEFAULT NULL,
  PRIMARY KEY (`employee_id`),
  INDEX `idx_department` (`department`),
  INDEX `idx_gender` (`gender`),
  INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO `employees`
  (`employee_id`, `name`, `department`, `position`, `level`, `salary`, `hire_date`, `status`, `gender`, `age`)
VALUES
  ('E0001', 'Zhang Wei', 'R&D',     'Backend Engineer',  'P6', 28000.00, '2019-03-12', 'active',   'male',   31),
  ('E0002', 'Li Na',     'R&D',     'Frontend Engineer', 'P5', 22000.00, '2020-07-01', 'active',   'female', 28),
  ('E0003', 'Wang Qiang','Market',  'Market Manager',    'M1', 25000.00, '2018-11-20', 'active',   'male',   35),
  ('E0004', 'Liu Yang',  'Market',  'Marketing Spec',    'P4', 15000.00, '2021-02-15', 'active',   'male',   26),
  ('E0005', 'Chen Jing', 'HR',      'HRBP',              'P5', 18000.00, '2019-09-09', 'active',   'female', 30),
  ('E0006', 'Yang Min',  'Finance', 'Accountant',        'P4', 16000.00, '2020-01-08', 'active',   'female', 29),
  ('E0007', 'Zhao Lei',  'R&D',     'Algorithm Engineer','P7', 35000.00, '2017-05-23', 'active',   'male',   38),
  ('E0008', 'Sun Li',    'Finance', 'Finance Manager',   'M1', 30000.00, '2016-12-01', 'inactive', 'female', 41);
