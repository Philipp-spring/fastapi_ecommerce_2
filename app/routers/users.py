from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi.security import OAuth2PasswordRequestForm
from typing import Annotated

import jwt # библиотека - PyJWT (отвечает за создание (кодирование) и проверку (декодирование) JWT-токенов (JSON Web Tokens))
from app.config import SECRET_KEY, ALGORITHM # секретный ключ и алгоритм
from app.models.users import User as UserModel # ORM-модель
from app.schemas import UserCreate, User as UserSchema, RefreshTokenRequest # Pydantic-модели
from app.db_depends import get_async_db # асинхронная сессия
from app.auth import hash_password, verify_password, create_access_token, create_refresh_token  # функция создания пароля, проверки пароля, создания токена

router = APIRouter(prefix='/users', tags=['users'])

# Создание/регистрация пользователя
@router.post('/', response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_async_db)]):
    """
    Регистрирует нового пользователя с ролью 'buyer' или 'seller'.
    """
    # Проверка уникальности email
    result = await db.scalars(select(UserModel).where(UserModel.email == user.email))
    if result.first(): # если "email" уже существует - ОШИБКА
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, # Статус-код HTTP_409_CONFLICT (Конфликт) - означает, что запрос пользователя не может быть выполнен, потому что он нарушает текущие правила или состояние данных в базе (В веб-разработке и REST API этот код чаще всего используется ровно в одной ситуации: при попытке зарегистрировать аккаунт на email, который уже занят другим пользователем) («В самой базе данных всё настроено правильно, но то, что ты пытаешься туда записать прямо сейчас, физически не может там поместиться из-за того, что там уже лежит)
                            detail="Email already registered")
    # Создание объекта пользователя с хешированным паролем
    db_user = UserModel(                # <--в данном случае делаем не через **model_dump(), а присваиваем каждый параметр по отдельности
        email=user.email,               # остальные поля "id" и "is_active" присваиваются АВТОМАТИЧЕСКИ, потому что в них стоит параметр "primary_key=True" и "default=True" соответственно
        hashed_password=hash_password(user.password.get_secret_value()), # <--берет чистый, открытый пароль, который пользователь ввел при регистрации, засаливает и шифрует его, а затем передает готовый безопасный хэш в модель базы данных UserModel.
        role=user.role                                                   # get_secret_value() — функция которая используется для безопасного извлечения чистого текстового значения из полей с типом SecretStr или SecretBytes (объект-сейф)
    )
    # Добавление в сессию и сохранение в базе
    db.add(db_user)
    await db.commit() # Поля 'id' и 'is_active' НЕ НУЖНО передавать вручную при создании объекта. В самой модели для 'id' задан 'primary_key=True' (СУБД автоматически сгенерирует его через автоинкремент), а для 'is_active' задан 'default=True' (SQLAlchemy/БД подставит True автоматически).
    return db_user # Таблица в БД уже была создана ЗАРАНЕЕ (через Alembic или Base.metadata.create_all).
                   # После вызова 'db.commit()' физически создается новая СТРОКА (запись) в этой таблице.


# hashed_password=hash_password(user.password.get_secret_value())
# Пароль должен хешироваться с помощью функции hash_password() перед сохранением в базу данных, чтобы обеспечить безопасность. Сохранение пароля в открытом виде (user.password) недопустимо.

# HTTP_409_CONFLICT
# Состояние данных в базе - Это когда операция не может завершиться, потому что база данных прямо сейчас заполнена определенным образом. (Пример с Email: Хакер или обычный юзер пытается зарегистрировать почту vlad@mail.ru. Но в таблице users на жестком диске уже лежит строка, где в колонке email написано vlad@mail.ru. Возникает конфликт с текущим состоянием данных. База говорит: «Я не могу создать второго такого же, место под эту почту занято!» )
# Текущие правила базы - Правила — это ограничения (Constraints), которые ты сам прописал в коде модели SQLAlchemy, когда создавал таблицы


# эндпоинт создания/генерации токена (отдаёт 2 токена "access" и "refresh")
@router.post("/token") # Этот маршрут обычно используется в OAuth2 для получения токена доступа (Access Token)                                                      Сам класс OAuth2PasswordRequestForm жестко закодирован под конкретную задачу — используется только для первичного входа в аккаунт (для логина/аутентификации) по логину и паролю. Внутри него есть только два обязательных поля: username и password.
async def login(form_data: OAuth2PasswordRequestForm = Depends(), # отвечает за получение данных формы, отправленных в формате "application/x-www-form-urlencoded". Класс "OAuth2PasswordRequestForm" из "FastAPI" автоматически извлекает из запроса поля "username" и "password" (логин и пароль пользователя). "username" и "password" - такое именование жестко закреплено в официальной международной спецификации протокола OAuth 2.0 (RFC 6749).
                db: AsyncSession = Depends(get_async_db)): # FastAPI - автоматически вызывает этот класс OAuth2PasswordRequestForm через Depends при каждом входящем запросе. Сам парсит тело запроса, но ищет данные не в формате JSON, а в формате HTML-формы (application/x-www-form-urlencoded), как требует официальный стандарт OAuth2. Автоматически проверяет, пришли ли обязательные поля username (куда обычно передают email или логин) и password. Если их нет, он сам вернет ошибку 422 Unprocessable Entity. Собирает эти данные в удобный объект (обычно его называют form_data), из которого вы потом в коде просто забираете значения через точку: form_data.username и form_data.password
# Оба аргумента внедряются через механизм зависимостей FastAPI (Depends). В FastAPI инструмент Depends() — это универсальный механизм для ПОЛУЧЕНИЯ любых данных, которые не являются простыми Query-параметрами или обычным JSON-телом запроса. Потому что в FastAPI классы (такие как "OAuth2PasswordRequestForm") не имеют прямого доступа к HTTP-запросу интернета. Они не умеют «слышать» сеть сами по себе. Без Depends() класс остался бы «слепым».
    """
    Аутентифицирует пользователя и возвращает JWT с email, role и id.
    """
    result = await db.scalars( # для проверки пользователя код выполняет запрос к базе данных. (SQL-запрос)
        select(UserModel).where(UserModel.email == form_data.username, UserModel.is_active == True)) # ищем по логину (email).
    user = result.first() # если пользователь не найден (например, email отсутствует в базе), user будет "None"
    if not user or not verify_password(form_data.password, user.hashed_password): # <--проверка существует ли пользователь и корректен ли его пароль. Функция verify_password (определённая у нас в app.auth) использует библиотеку "passlib" для сравнения пароля из формы с хешированным паролем из базы (поле user.hashed_password).
        raise HTTPException( # Если хотя бы одно из условий не выполнено, выбрасывается исключение HTTPException с кодом 401 (Unauthorized), сообщением "Incorrect email or password" и заголовком WWW-Authenticate: Bearer, что соответствует стандартам OAuth2.
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Если аутентификация успешна, создаются два JWT-токена.  "create_access_token" и "create_refresh_token" (определённые у нас в app.auth) принимают словарь data с полями sub (email пользователя), role (роль пользователя) и id (ID пользователя).
    access_token = create_access_token(data={"sub": user.email, "role": user.role, "id": user.id}) # Она генерирует токен с использованием библиотеки "PyJWT", добавляя срок действия (exp) и подписывая токен с помощью секретного ключа и алгоритма, указанных в "SECRET_KEY" и "ALGORITHM". ( Полученный токен сохраняется в переменную "access_token")
    refresh_token = create_refresh_token(data={"sub": user.email, "role": user.role, "id": user.id})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"} # возвращает словарь (который FastAPI преобразует в JSON) с тремя ключами: "access_token", "refresh_token" (содержат сгенерированный JWT) и "token_type" (с значением bearer, указывающим, что это токен типа Bearer для использования в заголовках Authorization). Этот ответ соответствует стандарту OAuth2 и может быть использован клиентом для последующих авторизованных запросов.

# В этом коде мы обращаемся к create_access_token и create_refresh_token, которые создают JWT-токены с одинаковым payload (sub, role, id), но разным временем истечения (exp) и ролью (token_type).
# Возвращает оба токена в JSON-ответе. Клиент должен сохранить их (например, в переменных фронтенда).  Если email не найден или пароль неверный, возвращается 401 Unauthorized с заголовком WWW-Authenticate: Bearer.

# OAuth 2.0 (Open Authorization) — это открытый протокол авторизации, который позволяет одному приложению получить ограниченный доступ к защищенным ресурсам пользователя на другом сервисе без передачи ему логина и пароля
# OAuth 2.0 работает как электронный пропуск (токен). Вместо того чтобы отдавать сайту свой пароль от Google или VK, вы разрешаете Google выдать этому сайту временный ключ с ограниченными правами (например, только на чтение вашего email)
# Протокол - набор четких правил и стандартов, которые определяют, как разные программы, устройства или серверы должны общаться между собой, чтобы понимать друг друга.

# Bearer (в переводе с английского — «предъявитель» или «носитель») — это схема аутентификации, которая дает доступ к ресурсу любому, кто просто предъявит этот токен.


# Обновление refresh-токена (в этом эндпоинте "refresh-token" проверяется)
@router.post("/refresh-token")
async def refresh_token(
    body: RefreshTokenRequest, # принимает JSON старый refresh-токен в в теле POST-запроса (в формате application/x-www-form-urlencoded или application/json(в нашем случае Pydantic)) (по официальным мировым стандартом OAuth 2.0) (Pydantic-схема RefreshTokenRequest)
    db: AsyncSession = Depends(get_async_db), # Если бы вы передавали refresh_token тоже в заголовке Authorization, вашей системе было бы технически очень трудно понять: это пришел просроченный access-токен или это пришел рабочий refresh-токен? Передача в теле (body) изолирует этот процесс. Бэкенд четко знает: «Если токен лежит в теле схемы RefreshTokenRequest, значит, пользователь пришел не смотреть страницы, он пришел заключить сделку по обмену токенов».
    ):
    """
    Обновляет refresh-токен, принимая старый refresh-токен в теле запроса.
    """
    credentials_exception = HTTPException(  # исключение - учетных данных
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
        headers={"WWW-Authenticate": "Bearer"}, # <--уведомление для клиента (фронтенда) о том, что сервер требует авторизацию в формате Bearer (токен формата Bearer).
    )

    old_refresh_token = body.refresh_token # извлекает строку токена из поля "refresh_token" в ТЕЛЕ запроса

    try: # попытка декодирования
        payload = jwt.decode(old_refresh_token, SECRET_KEY, algorithms=[ALGORITHM]) # На этом этапе метод jwt.decode() проверяются подпись JWT, срок действия (exp) и корректность структуры. Если токен испорчен, просрочен или подписан другим ключом, то метод выбрасывает исключение, которое ниже перехватывается в блоке except для возврата ошибки "401 Unauthorized". В случае успеха "Header" и "Signature" отбрасываются, остается только "Payload". Функция берёт сырую строку токена, которую прислал клиент и пытается её декодировать и проверить подпись. SECRET_KEY - секретный ключ, который знает только бэкенд. Метод decode использует его, чтобы проверить цифровую подпись токена. algorithms=[ALGORITHM] - Указывает, какой именно математический алгоритм хеширования (обычно HS256) нужно использовать для проверки подписи. (Если токен валиден, в переменную "payload" возвращается обычный Python-словарь с данными, которые были зашиты в токен (их называют claims или заявления))
        email: str | None = payload.get("sub") # <--получает из payload email пользователя
        token_type: str | None = payload.get("token_type") # <--получает из payload тип токена

        # Проверяем, что токен действительно refresh
        if email is None or token_type != "refresh": # если email (поле sub) НЕ существует ИЛИ тип токена НЕ "refresh"
            raise credentials_exception # ОШИБКА

    except jwt.ExpiredSignatureError: # ExpiredSignatureError — это частный случай ошибки (конкретно истекший срок действия). «От частного к общему»
        # refresh-токен истёк
        raise credentials_exception
    except jwt.PyJWTError: # PyJWTError — это общий (базовый) класс для абсолютно всех ошибок библиотеки PyJWT.
        # подпись неверна или токен повреждён
        raise credentials_exception

    # Проверяем, что пользователь существует и активен (Это нужно для того, чтобы заблокированный или удалённый пользователь не мог обновлять свои токены)
    result = await db.scalars(
        select(UserModel).where(
            UserModel.email == email,
            UserModel.is_active == True
        )
    )
    user = result.first()
    if user is None: # Если пользователь не найден или помечен как неактивный
        raise credentials_exception # ОШИБКА

    # Генерируем новый refresh-токен
    new_refresh_token = create_refresh_token( # создаёт новый refresh-токен, копируя основные данные (sub, role, id) и задавая новый срок действия.
        data={"sub": user.email, "role": user.role, "id": user.id} # Срок действия (exp) и тип токена (token_type="refresh") генерируются внутри самой функции create_refresh_token
    )

    return {
        "refresh_token": new_refresh_token, #  возвращает новый refresh-токен
        "token_type": "bearer", # Слово "bearer" (в переводе «предъявитель») — это общепринятый стандарт OAuth2. Это инструкция для фронтенда, которая говорит: «Когда будешь отправлять мне этот токен обратно, положи его в HTTP-заголовок Authorization и добавь перед ним слово Bearer». (Например: Authorization: Bearer <ваш_токен>).
    }






# Получение нового access-токена по действующему refresh-токену
@router.post("/new-access-token")
async def new_access_token(
    body: RefreshTokenRequest, # refresh-токен приниматеся либо в теле запроса (Request Body) через JSON либо в защищенных Куках (HttpOnly Cookies)(Самый безопасный вариант для сайтов)
    db: Annotated[AsyncSession, Depends(get_async_db)]
    ):
    """
    Получение нового access-токена по действующему refresh-токену.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
        headers={"WWW-Authenticate": "Bearer"}  # headers — это параметр класса "HTTPException" (Он позволяет передать клиенту дополнительные HTTP-заголовки (HTTP Headers) вместе с ответом об ошибке.)
    )

    refresh_token = body.refresh_token # <---переменная внутри Pydantic-схемы "RefreshTokenRequest" (извлекаем СТРОКУ токена из тела запроса)

    try: # попытка декодирования
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM]) # (Поля токена: "Header"(проверяет),  Payload(превращает_в_словарь), "Signature"(проверяет))
        email: str | None = payload.get('sub') # <--получает из payload email пользователя
        token_type: str | None = payload.get('token_type') # <--получает из payload тип токена

        # Проверяем, что токен действительно refresh
        if email is None or token_type != "refresh":
            raise credentials_exception

    except jwt.ExpiredSignatureError: # (ExpiredSignatureError перевод: Истек срок действия подписи)
        raise credentials_exception # refresh-токен истёк (в данном задании нужен именно ДЕЙСТВУЮЩИЙ refresh-токен)
    except jwt.PyJWTError: # подпись неверна или токен повреждён
        raise credentials_exception


    # Проверяем, что пользователь существует и активен (Это нужно для того, чтобы заблокированный или удалённый пользователь не мог обновлять свои токены)
    user = await db.scalar(
        select(UserModel).where(
            UserModel.email == email,
            UserModel.is_active == True
        )
    )

    if user is None:  # Эта проверка нужна, чтобы заблокированный пользователь не мог использовать свой токен, который ещё может быть активен. (Сервер без этого кода не знает, что пользователя уже забанили, ведь подпись на токене всё еще правильная)
        raise credentials_exception

    # Генерируем новый access-токен
    new_access_token = create_access_token( # функция create_access_token задает новое время токену автоматически при каждом её вызове
        data = {"sub": user.email, "role":user.role, "id": user.id}
    )                                       # в текущем коде РОТАЦИЯ НЕ включена (refresh-токен остается СТАРЫМ)
    return {"access_token": new_access_token, "token_type": "bearer"}


# Ротация токенов (Refresh Token Rotation) — это защитный механизм, при котором каждый раз, когда пользователь использует свой refresh_token для получения нового access_token, сервер аннулирует старый refresh_token и выдает клиенту абсолютно новый refresh_token вместе с новым access_token



























































































