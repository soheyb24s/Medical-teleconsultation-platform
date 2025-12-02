from django.urls import path
from . import views
from . import api

urlpatterns = [
    path('', views.index, name='index'),  # الصفحة الرئيسية
    path('patient/register/', views.patient_register, name='patient_register'),
    path('patient/login/', views.patient_login, name='patient_login'),
    path('patient/interface/', views.patient_interface, name='patient_interface'),  # إضافة مسار واجهة المريض
    path('doctor/login/', views.doctor_login, name='doctor_login'),  # صفحة تسجيل دخول الطبيب
    path('doctor/interface/', views.doctor_interface, name='doctor_interface'),
    path('consultation/<int:consultation_id>/', views.consultation_room, name='consultation_room'),
    path('admin-login/', views.admin_login, name='admin_login'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('logout/', views.logout_view, name='logout'),
    
    # API Endpoints
    path('api/available-slots/', api.get_available_slots, name='api_available_slots'),
    path('api/book-appointment/', api.book_appointment, name='api_book_appointment'),
    path('api/cancel-appointment/', api.cancel_appointment, name='api_cancel_appointment'),
    path('api/update-doctor-availability/', api.update_doctor_availability, name='api_update_doctor_availability'),
    path('api/delete-doctor-availability/', api.delete_doctor_availability, name='api_delete_doctor_availability'),
    path('api/doctors/', api.get_doctors_by_speciality, name='api_doctors_by_speciality'),
    path('api/available-dates/', api.get_available_dates, name='api_available_dates'),
    path('api/accept-appointment/', api.accept_appointment, name='api_accept_appointment'),
    path('api/refuse-appointment/', api.refuse_appointment, name='api_refuse_appointment'),
    path('api/mark-notification-read/', api.mark_notification_read, name='api_mark_notification_read'),
    path('api/confirm-consultation/', api.confirm_consultation, name='api_confirm_consultation'),
    path('api/check-consultation-status/', api.check_consultation_status, name='api_check_consultation_status'),
    path('api/end-consultation/', api.end_consultation, name='api_end_consultation'),
    path('api/consultation/<int:consultation_id>/', views.get_consultation_details, name='get_consultation_details'),
    path('api/update-profile/', api.update_profile, name='update_profile'),
    path('api/update-profile/', api.update_profile, name='update_profile'),
]






