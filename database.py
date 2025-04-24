import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import declarative_base
from supabase import create_client

# 환경변수 로드
load_dotenv()

# Supabase 연결
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

# SQLAlchemy 설정
db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)
metadata = MetaData(schema="trip_to_travel")
Base = declarative_base(metadata=metadata)