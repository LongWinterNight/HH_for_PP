#!/usr/bin/env python3
"""Тестовый сервер для отладки."""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from src.storage import VacancyStorage

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Test API"}

@app.get("/api/test")
def test_endpoint():
    return {"test": "ok", "message": "Hello World"}

@app.get("/api/vacancies")
def get_vacancies(page: int = 1, per_page: int = 20):
    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        total = len(df)
        
        # Простая пагинация
        start = (page - 1) * per_page
        end = start + per_page
        df_page = df.iloc[start:end]
        
        # Конвертация в dict
        items = []
        for _, row in df_page.iterrows():
            item = {}
            for col in df.columns:
                val = row.get(col)
                if pd.isna(val):
                    val = None
                elif hasattr(val, 'isoformat'):  # datetime
                    val = str(val)
                else:
                    val = val
                item[col] = val
            items.append(item)
        
        return {"total": total, "page": page, "items": items}
    finally:
        storage.close()

if __name__ == "__main__":
    import uvicorn
    print("Starting test server on http://localhost:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=False)
