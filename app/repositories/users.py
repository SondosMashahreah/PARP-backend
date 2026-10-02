from app.models.user import User


def by_email(db, email):
    return db.query(User).filter(User.email == email).first()


def by_id(db, user_id):
    return db.query(User).filter(User.id == user_id).first()


def add(db, user):
    db.add(user)
    db.flush()


def commit(db):
    db.commit()


def refresh(db, user):
    db.refresh(user)


def rollback(db):
    db.rollback()
