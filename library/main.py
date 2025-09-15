from fastapi import FastAPI, HTTPException, Query, Depends #⬅️⬅️
from sqlalchemy.orm import Session #⬅️⬅️
from pydantic import BaseModel, Field
from typing import Annotated
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta



from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import Request


templates = Jinja2Templates(directory="templates")

import models, schemas, crud #⬅️⬅️
from database import engine, Base, SessionLocal #⬅️⬅️

# Створюємо таблиці у базі
Base.metadata.create_all(bind=engine) #⬅️⬅️

app = FastAPI()

# Dependency для отримання сесії БД
def get_db(): #⬅️⬅️
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----- Автори -----
@app.post("/authors/", response_model=schemas.Author)
def create_author(author: schemas.AuthorCreate, db: Session = Depends(get_db)):
    db_author = crud.get_author_by_name(db, name=author.name)
    if db_author:
        raise HTTPException(status_code=409, detail="Автор вже існує")
    return crud.create_author(db=db, author=author)


@app.get("/authors/", response_model=list[schemas.Author])
def get_authors(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_authors(db, skip=skip, limit=limit)


@app.get("/authors/{author_id}", response_model=schemas.Author)
def get_author(author_id: int, db: Session = Depends(get_db)):
    db_author = crud.get_author(db, author_id=author_id)
    if not db_author:
        raise HTTPException(status_code=404, detail="Автор не знайдений")
    return db_author


# ----- Книги -----

@app.post("/books/", response_model=schemas.Book)
def create_book(book: schemas.BookCreate, db: Session = Depends(get_db)):
    # перевірка на існування автора
    db_author = crud.get_author(db, author_id=book.author_id)
    if not db_author:
        raise HTTPException(status_code=404, detail="Автор не знайдений")

    # перевірка на дубль книги
    db_books = crud.get_books(db)
    for b in db_books:
        if b.name.lower() == book.name.lower() and b.author_id == book.author_id:
            raise HTTPException(status_code=409, detail="Книга вже існує у цього автора")

    return crud.create_book(db=db, book=book)


@app.get("/books/", response_model=list[schemas.Book])
def get_books(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_books(db, skip=skip, limit=limit)


@app.get("/books/{book_id}", response_model=schemas.Book)
def get_book(book_id: int, db: Session = Depends(get_db)):
    db_book = crud.get_book(db, book_id=book_id)
    if not db_book:
        raise HTTPException(status_code=404, detail="Книга не знайдена")
    return db_book

# pip install "uvicorn[standard]"
# uvicorn main:app --reload
# main - назва вашого файлу


SECRET_KEY = "super_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@app.post("/register", response_model=schemas.User)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # Перевіряємо, чи існує користувач
    existing_user = crud.get_user(db, login=user.login)
    if existing_user:
        raise HTTPException(status_code=409, detail="User already exists")

    # Створюємо користувача
    new_user = crud.create_user(db, login=user.login, password=user.password)

    # Повертаємо дані користувача (без пароля)
    return schemas.User(id=new_user.id, login=new_user.login)


@app.post("/token")
async def token_get(
    form_data: OAuth2PasswordRequestForm = Depends(),  # отримує дані з форми логіну (username & password)
    db: Session = Depends(get_db)                       # підключення до бази даних через залежність
):
    # перевіряємо користувача та пароль у БД
    user = crud.authenticate_user(db, login=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    # створюємо JWT токен з терміном дії
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.login},       # "sub" зберігає у токені логін користувача
        expires_delta=access_token_expires
    )

    # повертаємо токен клієнту
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/protected")
async def protected(token: str = Depends(oauth2_scheme),  # отримує токен із заголовка Authorization
                    db: Session = Depends(get_db)):
    try:
        # розшифровуємо токен та отримуємо login користувача
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        login: str = payload.get("sub")
        if login is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # перевіряємо наявність користувача у БД
    user = crud.get_user(db, login=login)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # повертаємо захищене повідомлення
    return {"msg": f"{user.login}, welcome to the admin panel!"}


@app.get("/home", response_class=HTMLResponse)
def ui_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/home/authors", response_class=HTMLResponse)
def ui_authors(request: Request, db: Session = Depends(get_db)):
    authors = crud.get_authors(db)
    return templates.TemplateResponse("authors.html", {"request": request, "authors": authors})




@app.get("/home/books", response_class=HTMLResponse)
def ui_books(request: Request, db: Session = Depends(get_db)):
    books = crud.get_books(db)
    return templates.TemplateResponse("books.html", {"request": request, "books": books})


@app.get("/home/authors/{author_id}",  response_class=HTMLResponse)
def ui_single_author(author_id: int, request: Request, db: Session = Depends(get_db)):
    db_author = crud.get_author(db, author_id=author_id)
    if not db_author:
        raise HTTPException(status_code=404, detail="Автор не знайдений")
    # отримуємо книжки саме цього автора
    books = db_author.books
    return templates.TemplateResponse(
        "author.html",
        {
            "request": request,
            "author": db_author,
            "books": books
        }
    )
# pip install "uvicorn[standard]"
# uvicorn main:app --reload
# main - назва вашого файлу

# pip install python-multipart
# pip install "python-jose[cryptography]"
# pip install "passlib[bcrypt]"

# python-multipart → потрібна для обробки форм у POST-запитах, особливо для OAuth2PasswordRequestForm у FastAPI.
# python-jose[cryptography] → реалізація JWT-токенів (шифрування, підпис, декодування).
# passlib[bcrypt] → для хешування паролів безпечним алгоритмом bcrypt.