from .categories import Category # в этой же папке(ORM-моделей) файл "categories.py" импортируем из него класс "Category"
from .products import Product # в этой же папке(ORM-моделей) файл "products.py" импортируем из него класс "Product"
from .users import User
from .reviews import Review
from .cart_items import CartItem
from .orders import Order, OrderItem

# импортирует наши ORM-модели, потому что они служат для "alembic" «чертежом» или эталоном того, как должна выглядеть база данных (Без этих моделей Alembic буквально «слеп» — он не знает, какие таблицы вы хотите создать в базе данных, какие колонки в них должны быть и какие типы данных использовать.)
# Он в файле "env.py" смотрит в свой параметр "target_metadata = Base.metadata" (куда как раз и подгрузились наши ORM-модели "Category" и "Product" благодаря импорту пакета models)

__all__ = ["Category", Order, OrderItem, "Product", "User", "Review", "CartItem"] # Это специальная переменная Python (список строк), которая определяет «белый список» объектов пакета.
# Если другой программист напишет во внешнем файле импорт через звездочку: from app.models import *, то Python импортирует только классы "Category", "Product" и "User". Все остальные внутренние функции, переменные или сторонние библиотеки, которые могут быть импортированы внутри файлов categories.py или products.py, наружу не выйдут.

# Точка перед именем (.categories) означает относительный импорт внутри ТЕКУЩЕГО каталога








