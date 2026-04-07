-- ============================================================
-- Инициализация PostgreSQL — создание схемы БД
-- ============================================================
-- Выполняется автоматически при первом запуске контейнера
-- ============================================================

-- Таблица вакансий
CREATE TABLE IF NOT EXISTS vacancies (
    id SERIAL PRIMARY KEY,
    vacancy_id VARCHAR(50) UNIQUE NOT NULL,
    vacancy_name VARCHAR(500) NOT NULL,
    published_at TIMESTAMP,
    applied_at TIMESTAMP,
    all_skills TEXT,
    hard_skills TEXT,
    soft_skills TEXT,
    tools TEXT,
    skill_count INTEGER DEFAULT 0,
    hard_skill_count INTEGER DEFAULT 0,
    soft_skill_count INTEGER DEFAULT 0,
    tools_count INTEGER DEFAULT 0,
    salary_from FLOAT,
    salary_to FLOAT,
    salary_currency VARCHAR(10) DEFAULT 'RUB',
    salary_gross BOOLEAN DEFAULT FALSE,
    employer_name VARCHAR(300),
    employer_id VARCHAR(50),
    employer_url VARCHAR(500),
    vacancy_url VARCHAR(500),
    experience VARCHAR(100),
    employment VARCHAR(100),
    schedule VARCHAR(100),
    area VARCHAR(200),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Индексы для ускорения запросов
CREATE INDEX IF NOT EXISTS idx_vacancy_id ON vacancies (vacancy_id);
CREATE INDEX IF NOT EXISTS idx_employer ON vacancies (employer_name);
CREATE INDEX IF NOT EXISTS idx_area ON vacancies (area);
CREATE INDEX IF NOT EXISTS idx_published_at ON vacancies (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_experience ON vacancies (experience);
CREATE INDEX IF NOT EXISTS idx_salary_from ON vacancies (salary_from);
CREATE INDEX IF NOT EXISTS idx_created_at ON vacancies (created_at);

-- Таблица журнала парсингов
CREATE TABLE IF NOT EXISTS parser_runs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'running',
    keywords TEXT,
    max_pages INTEGER DEFAULT 10,
    days_back INTEGER DEFAULT 30,
    is_incremental BOOLEAN DEFAULT TRUE,
    use_cache BOOLEAN DEFAULT TRUE,
    vacancies_collected INTEGER DEFAULT 0,
    vacancies_new INTEGER DEFAULT 0,
    vacancies_updated INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Таблица настроек приложения
CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_parse_at TIMESTAMP,
    last_successful_parse_at TIMESTAMP,
    total_parses INTEGER DEFAULT 0,
    total_vacancies_collected INTEGER DEFAULT 0,
    app_version VARCHAR(20) DEFAULT '2.0.0',
    config_version VARCHAR(20),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Инициализация настроек (синглтон)
INSERT INTO app_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- Таблица кэша API (опционально, можно использовать внешний Redis)
CREATE TABLE IF NOT EXISTS api_cache (
    url TEXT PRIMARY KEY,
    response_json JSONB,
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cache_timestamp ON api_cache (timestamp);

COMMENT ON TABLE vacancies IS 'Основная таблица вакансий с HH.ru';
COMMENT ON TABLE parser_runs IS 'Журнал всех запусков парсера';
COMMENT ON TABLE app_settings IS 'Глобальные настройки приложения (синглтон, id=1)';
COMMENT ON TABLE api_cache IS 'Кэш запросов к HH API';
