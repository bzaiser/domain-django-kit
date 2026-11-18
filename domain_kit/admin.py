from django.contrib import admin

from .models import (
    Address,
    AssetItem,
    Category,
    Document,
    DomainGroupPermission,
    DomainModuleSettings,
    Person,
    Role,
    Status,
    Unit,
)

admin.site.register(DomainModuleSettings)
admin.site.register(DomainGroupPermission)
admin.site.register(Category)
admin.site.register(Unit)
admin.site.register(Status)
admin.site.register(Role)
admin.site.register(Person)
admin.site.register(Address)
admin.site.register(AssetItem)
admin.site.register(Document)
