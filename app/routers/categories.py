from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status # <--импортирует класс для создания маршрутизатора
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.categories import Category as CategoryModel         # импортируем ORM-модели (псевдоним, чтобы не было конфликта)
from app.schemas import Category as CategorySchema, CategoryCreate  # импортируем Pydantic-модели (псевдоним, чтобы не было конфликта)
from app.db_depends import get_db                                   # импортируем функцию сессии (зависимость для эндпоинтов)

from app.models.users import User as UserModel # ORM-модель
from app.auth import get_current_admin # функция проверки роли админа (admin)

from sqlalchemy.ext.asyncio import AsyncSession # (асинхронный аналог Session)
from app.db_depends import get_async_db # функция-зависимость предоставляющая асинхронную сессию

# Создаём маршрутизатор с префиксом и тегом
router = APIRouter(
    prefix="/categories", # <--строка, добавляемая к началу всех маршрутов. Все эндпоинты в этом файле начинаются с /categories (Например, @router.get("/") станет /categories/)
    tags=["categories"],  # <--список строк для группировки эндпоинтов в документации. В Swagger UI эти эндпоинты будут сгруппированы под заголовком "categories"
)

# Docstrings: Строки документации (в тройных кавычках) отображаются в Swagger UI, помогая другим разработчикам понять назначение эндпоинта.

@router.get("/", response_model=list[CategorySchema]) # <--для пользователя и фронтенда это адрес: /categories
async def get_all_categories(db: Annotated[AsyncSession, Depends(get_async_db)]): # status_code - по умолчанию 200
    """
    Возвращает список всех (активных) категорий товаров.
    """
    stmt = select(CategoryModel).where(CategoryModel.is_active == True)
    result  = await db.scalars(stmt)               # синхронно: db.scalars(stmt).all()
    categories = result.all()
    return categories


@router.post("/", response_model=CategorySchema, status_code=status.HTTP_201_CREATED)
async def create_category(
        category: CategoryCreate,
        db: AsyncSession = Depends(get_async_db),
        current_user: UserModel = Depends(get_current_admin) # зависимость "get_current_admin" - функция проверки роли админа (admin), внутри которой вызывается функция "get_current_user"
):

    """
    Создаёт новую категорию, привязанную к текущему продавцу (только для 'admin').
    """
    # Проверка существования parent_id, если указан
    if category.parent_id is not None: # проверяем есть ли такой родитель в БД и активен ли он
        stmt = select(CategoryModel).where(CategoryModel.id == category.parent_id, CategoryModel.is_active == True)
        result = await db.scalars(stmt) # синхронно: db.scalars(stmt).first()
        parent = result.first()
        if parent is None:
            raise HTTPException(status_code=400, detail="Parent category not found")
    # Создание новой категории
    db_category = CategoryModel(**category.model_dump(), admin_id=current_user.id) # "admin_id=current_user.id" - пристыковываем к категории ID того администратора, который прямо сейчас делает этот запрос (его личность подтвердила наша цепочка зависимостей на основе JWT)
    db.add(db_category)
    await db.commit()
    await db.refresh(db_category)
    return db_category

# При expire_on_commit=False данные объекта db_category остаются нетронутыми в оперативной памяти (кэше сессии)
# При expire_on_commit=False данные в ОЗУ помечаются устаревшими сразу после .commit()

# Для этого конкретного примера на PostgreSQL (и других СУБД с поддержкой RETURNING, которую использует SQLAlchemy) после await db.commit() объект обычно УЖЕ СОДЕРЖИТ значения,
# сгенерированные БД, поэтому результат ответа будет таким же и без await db.refresh(db_product).

@router.put("/{category_id}", response_model=CategorySchema) # {category_id} извлекается FastAPI автоматически, а тип int обеспечивает валидацию (если передать не число, FastAPI вернёт ошибку 422)
async def update_category(
        category_id: int,
        category: CategoryCreate,
        db: Annotated[AsyncSession, Depends(get_async_db)],
        current_user: UserModel = Depends(get_current_admin)
):
    """
    Обновляет категорию по её ID, если она принадлежит текущему админу (только для 'admin').
    """
    # Проверка существования категории
    stmt = select(CategoryModel).where(CategoryModel.id == category_id, CategoryModel.is_active == True) # <--нет await, т.к. мы не обращаемся к БД, а просто формируем запрос
    result = await db.scalars(stmt)
    db_category = result.first() # <--возвращает "CategoryModel" или "None"
    if db_category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if db_category.admin_id != current_user.id: # Проверяет владение категорией выбрасывая ошибку "403 Forbidden" («Запрещено») при попытке изменить чужую категорию.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update your own categories")
    # Проверка существования parent_id, если указан
    if category.parent_id is not None:
        parent_stmt = select(CategoryModel).where(CategoryModel.id == category.parent_id, CategoryModel.is_active == True)
        parent_result = await db.scalars(parent_stmt)
        parent = parent_result.first()
        if parent is None: # существует ли родитель
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent category not found")
        if parent.id == category_id: # проверяем, что категория не является родителем себя же на саму себя (для защиты сервера от бесконечной рекурсии (зависания и падения))
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category cannot be its own parent")

    # Обновление категории
    update_data = category.model_dump(exclude_unset=True)  # <---> exclude_unset=True <--(исключить_неустановленные)--> в итоговый словарь попали только те поля, которые были ЯВНО переданы при создании объекта category (вашей модели CategoryCreate). Если поля НЕ ПЕРЕДАНЫ пользователем, а ставятся по умолчанию, то они НЕ ПОПАДАЮТ в словарь "model_dump()". (ОДНАКО по стандарту HTTP, запрос PUT означает полную замену объекта.)
    await db.execute(update(CategoryModel).where(CategoryModel.id == category_id).values(**update_data))            # синхронно: db.execute(update(CategoryModel).where(CategoryModel.id == category_id).values(**category.model_dump())) # <--есть более правильный способ через setattr()
    await db.commit()
    await db.refresh(db_category) # <---тут обновление НЕ через цикл for (а только на стороне БД), поэтому refresh нужен. Так как в этом куске кода, мы обновляем ТОЛЬКО на стороне БД и "db_category" остается старым, и нам нужно его обновить на стороне ОЗУ, чтобы сделать "return db_category"
    return db_category




@router.delete("/{category_id}", status_code=status.HTTP_200_OK)
async def delete_category(
        category_id: int,
        db: Annotated[AsyncSession, Depends(get_async_db)],
        current_user: UserModel = Depends(get_current_admin)
):
    """
    Удаляет категорию по её ID, если она принадлежит текущему админу (только для 'admin').
    """
    # Проверка существования активной категории
    stmt = select(CategoryModel).where(CategoryModel.id == category_id, CategoryModel.is_active == True)
    result = await db.scalars(stmt)
    db_category = result.first()
    if db_category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    if db_category.admin_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own categories")

    # ЛОГИЧЕСКОЕ/(мягкое) удаление категории (установка is_active=False) - (по сути - обновление - update())
    stmt = update(CategoryModel).where(CategoryModel.id == category_id).values(is_active=False) # <--здесь в "stmt" лежит объект класса Update
    await db.execute(stmt)   # <--делаем обращение. execute() получает от "stmt" объект класса Update, поэтому scalars() тут не подходит, т.к. ожидает строки с данными. execute() - возвращает корутину и передает её await. await - возвращает Result
    await db.commit()
    await db.refresh(db_category)
    return db_category # <--мягкое удаление возвращает данные                                 <---(Плюсы: Идеально вписывается в концепцию REST API. Фронтенд (например, React или Vue) сразу видит обновленное состояние объекта в базе данных. Ему не нужно делать повторный GET-запрос, чтобы обновить состояние на экране — он может сразу использовать прилетевший JSON с is_active: false. Минусы: Пересылается чуть больше данных по сети.)
    # синхронное: return {"status": "success", "message": "Category marked as inactive"}      <---или можно так (Плюсы: Ответ весит очень мало (экономия трафика). Фронтенду легко понять, что всё ок.  Минусы: Требует создания отдельной Pydantic-схемы для ответа (например, class StatusResponse(BaseModel)), иначе FastAPI не сможет красиво задокументировать этот ответ в Swagger. Также фронтенд не получает актуальное состояние объекта.



# БОЛЕЕ ЛУЧШИЙ ВАРИАНТ логического удаления через изменение атрибута объекта, который уже и так получен из БД:          <-----вместо---> (db.execute(update(CategoryModel).where(CategoryModel.id == category_id).values(is_active=False)))
# category.is_active = False   <---здесь изменение атрибута происходит в объекте Python в ОЗУ
# 1. объект category в памяти Python сразу обновляется (Синхронность) -------> c update() изменялась база данных, но объект Python оставался старым
# 2. Отсутствие лишней нагрузки на сеть. Поскольку выше сделан запрос SELECT(stmt = select...), объект уже загружен в память.





# РАБОТА "current_user: UserModel = Depends(get_current_admin)":
# (Вызывается "get_current_admin", внутри которой вызывается "get_current_user")
# Шаг 1: Извлечение токена. Зависимость заглядывает в заголовок запроса и забирает строку токена. (с помощью "OAuth2PasswordBearer")
# Шаг 2: Расшифровка. Сервер проверяет срок действия токена, а также берет "SECRET_KEY" и проверяет подпись токена. Если подпись верна, то получает Payload, потом вытаскивает из Payload почту и проверяет её наличие в Payload (например, admin@example.com).
# Шаг 3: Поход в базу данных. Сервер открывает SQLAlchemy и делает запрос в БД: "select(UserModel).where(UserModel.email == email, UserModel.is_active == True))" и если пользователь есть и он активен, то пользователь - НАЙДЕН...  (т.е. по логину (email) ищется нужный нам пользователь)
# Шаг 4: Проверка роли. База данных возвращает строку пользователя. А зависимость "get_current_admin" проверяет поле роли: if user.role != "admin".
# Шаг 5: Передача в переменную. Если роль совпала, функция делает return user, и переменная "current_user" в эндпоинтах получает готовый объект "UserModel"





