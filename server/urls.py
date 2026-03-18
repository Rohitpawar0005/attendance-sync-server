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


# Temporary 500 handler — shows the actual error as plain text
def handler500_debug(request):
    import traceback, sys
    from django.http import HttpResponse
    exc_info = sys.exc_info()
    tb = ''.join(traceback.format_exception(*exc_info)) if exc_info[0] else 'No exception info available'
    return HttpResponse(
        f"<h1>500 — Debug Error</h1><pre>{tb}</pre>",
        content_type="text/html",
        status=500,
    )

handler500 = 'server.urls.handler500_debug'
