import certifi
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 1. Clean URL: Removed the ?ssl_mode=... part from the end
DATABASE_URL = "mysql+pymysql://4Mn57PuDVA37EaJ.root:5s4N4lJm15aDUHem@gateway01.ap-southeast-1.prod.alicloud.tidbcloud.com:4000/test"

# 2. Pass the SSL configuration directly to PyMySQL
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={
        "ssl": {
            "ca": certifi.where()  # Automatically provides the correct CA certificate path
        }
    }
)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()