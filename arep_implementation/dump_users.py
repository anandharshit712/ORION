import sys
sys.path.append('c:/Users/anand/Downloads/AUTONOMOUS ROBUSTNESS EVALUATION PLATFORM (AREP)/arep_implementation')
from arep.database.connection import get_session
from arep.database.models import UserRecord

session = get_session()
users = session.query(UserRecord).all()
for u in users:
    print(f"ID: {u.id}, Email: {u.email}, Username: {u.username}, Has Password: {bool(u.hashed_password)}")
    print(f"Hash: {u.hashed_password}")
session.close()
