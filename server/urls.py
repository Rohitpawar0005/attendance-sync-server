from django.contrib import admin
from django.urls import path
from api import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('core/api/sync/receive/', views.sync_receive, name='sync_receive'),
    path('core/api/sync/export/', views.sync_export, name='sync_export'),
    path('core/api/sync/status/', views.sync_status, name='sync_status'),
    path('core/api/sync/debug/', views.sync_debug, name='sync_debug'),
]

# Customize admin site header
admin.site.site_header = 'Edu Attend Sync Server'
admin.site.site_title = 'Edu Attend Sync'
admin.site.index_title = 'Manage School Data'
