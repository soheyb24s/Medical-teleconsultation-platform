from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import PatientRegistrationForm, PatientLoginForm, DoctorRegistrationForm, DoctorLoginForm
from django.contrib.auth.decorators import login_required
from .models import CustomUser, Patient, Doctor, LicenseNumber, Notification, Appointment, ConsultationRoom, Consultation
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime, timedelta

def index(request):
    return render(request, 'accounts/index.html')

def patient_register(request):
    if request.method == 'POST':
        form = PatientRegistrationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # إنشاء حساب المستخدم
                    user = form.save(commit=False)
                    user.username = form.cleaned_data['email']
                    user.email = form.cleaned_data['email']
                    user.is_patient = True
                    user.save()
                    
                    # إنشاء سجل المريض مع كلمة المرور المشفرة
                    Patient.objects.create(
                        user=user,
                        full_name=form.cleaned_data['full_name'],
                        email=form.cleaned_data['email'],
                        password=user.password  # نسخ كلمة المرور المشفرة
                    )
                    
                    messages.success(request, 'Inscription réussie!')
                    return redirect('patient_login')
            except Exception as e:
                messages.error(request, f'Une erreur est survenue lors de l\'inscription: {str(e)}')
    else:
        form = PatientRegistrationForm()
    return render(request, 'accounts/patient_register.html', {'form': form})

def patient_login(request):
    if request.method == 'POST':
        # التحقق مما إذا كان الطلب للتسجيل أم لتسجيل الدخول
        if 'register' in request.POST:
            # معالجة التسجيل
            full_name = request.POST.get('full_name')
            email = request.POST.get('email')
            password1 = request.POST.get('password1')
            password2 = request.POST.get('password2')

            if password1 != password2:
                messages.error(request, 'Les mots de passe ne correspondent pas')
                return render(request, 'accounts/patient_login.html')

            try:
                with transaction.atomic():
                    # إنشاء حساب المستخدم
                    user = CustomUser.objects.create_user(
                        username=email,
                        email=email,
                        password=password1,
                        is_patient=True
                    )
                    
                    # إنشاء سجل المريض مع كلمة المرور المشفرة
                    Patient.objects.create(
                        user=user,
                        full_name=full_name,
                        email=email,
                        password=user.password  # نسخ كلمة المرور المشفرة
                    )
                    
                    messages.success(request, 'Inscription réussie!')
                    return redirect('patient_login')
            except Exception as e:
                messages.error(request, f'Une erreur est survenue lors de l\'inscription: {str(e)}')
        else:
            # معالجة تسجيل الدخول
            email = request.POST.get('email')
            password = request.POST.get('password')
            user = authenticate(request, username=email, password=password)
            
            if user is not None and user.is_patient:
                try:
                    patient = Patient.objects.get(user=user)
                    login(request, user)
                    messages.success(request, 'Connexion réussie!')
                    return redirect('patient_interface')
                except Patient.DoesNotExist:
                    messages.error(request, 'Ce compte n\'existe plus. Veuillez créer un nouveau compte.')
                    return redirect('patient_login')
            else:
                messages.error(request, 'Email ou mot de passe incorrect')

    return render(request, 'accounts/patient_login.html')

def doctor_login(request):
    if request.method == 'POST':
        # التحقق مما إذا كان الطلب للتسجيل أم لتسجيل الدخول
        if 'register' in request.POST:
            # معالجة التسجيل
            full_name = request.POST.get('full_name')
            email = request.POST.get('email')
            password1 = request.POST.get('password1')
            password2 = request.POST.get('password2')
            license_number = request.POST.get('license_number')

            if password1 != password2:
                messages.error(request, 'Les mots de passe ne correspondent pas')
                return render(request, 'accounts/doctor_login.html')

            if len(password1) < 8:
                messages.error(request, 'Le mot de passe doit contenir au moins 8 caractères')
                return render(request, 'accounts/doctor_login.html')

            try:
                # التحقق من عدم وجود حساب بنفس البريد الإلكتروني
                if CustomUser.objects.filter(email=email).exists():
                    messages.error(request, 'Cet email est déjà utilisé')
                    return render(request, 'accounts/doctor_login.html')

                # التحقق من وجود حقل التخصص
                speciality = request.POST.get('speciality')
                if not speciality:
                    messages.error(request, 'Veuillez sélectionner une spécialité')
                    return render(request, 'accounts/doctor_login.html')

                # التحقق من صحة رقم الترخيص
                license_obj = LicenseNumber.objects.get(number=license_number)
                if not license_obj.is_valid:
                    messages.error(request, 'Le numéro de licence n\'est pas valide')
                    return render(request, 'accounts/doctor_login.html')
                
                if Doctor.objects.filter(license_number=license_number).exists():
                    messages.error(request, 'Ce numéro de licence est déjà utilisé')
                    return render(request, 'accounts/doctor_login.html')

                with transaction.atomic():
                    # إنشاء حساب المستخدم
                    user = CustomUser.objects.create_user(
                        username=email,
                        email=email,
                        password=password1,
                        is_doctor=True
                    )
                    
                    # إنشاء سجل الطبيب مع كلمة المرور المشفرة
                    Doctor.objects.create(
                        user=user,
                        full_name=full_name,
                        email=email,
                        password=user.password,
                        license_number=license_number,
                        is_verified=True,
                        speciality=request.POST.get('speciality')
                    )
                    
                    messages.success(request, 'Inscription réussie! Vous pouvez maintenant vous connecter.')
                    return redirect('doctor_login')
            except LicenseNumber.DoesNotExist:
                messages.error(request, 'Le numéro de licence n\'existe pas')
            except Exception as e:
                messages.error(request, f'Une erreur est survenue lors de l\'inscription: {str(e)}')
        else:
            # معالجة تسجيل الدخول
            email = request.POST.get('email')
            password = request.POST.get('password')
            
            if not email or not password:
                messages.error(request, 'Veuillez remplir tous les champs')
                return render(request, 'accounts/doctor_login.html')
            
            user = authenticate(request, username=email, password=password)
            
            if user is not None and user.is_doctor:
                try:
                    doctor = Doctor.objects.get(user=user)
                    if doctor.is_verified:
                        login(request, user)
                        messages.success(request, f'Bienvenue Dr. {doctor.full_name}!')
                        return redirect('doctor_interface')
                    else:
                        messages.error(request, 'Votre compte est en cours de vérification. Veuillez patienter.')
                        return render(request, 'accounts/doctor_login.html')
                except Doctor.DoesNotExist:
                    messages.error(request, 'Ce compte n\'existe plus. Veuillez créer un nouveau compte.')
                    return redirect('doctor_login')
            else:
                messages.error(request, 'Email ou mot de passe incorrect. Veuillez réessayer.')
                return render(request, 'accounts/doctor_login.html')

    return render(request, 'accounts/doctor_login.html')

@login_required
def doctor_interface(request):
    if not request.user.is_doctor:
        messages.error(request, 'Accès non autorisé. Veuillez vous connecter en tant que médecin.')
        return redirect('doctor_login')
    
    try:
        doctor = Doctor.objects.get(user=request.user)
        # جلب الإشعارات غير المقروءة للطبيب
        notifications = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).order_by('-created_at')
        
        # تعديل وقت الإشعارات (إنقاص ساعة)
        for notification in notifications:
            notification.created_at = notification.created_at - timedelta(hours=1)
        
        # جلب المواعيد المعلقة (للقسم mes rendez-vous)
        pending_appointments = Appointment.objects.filter(
            doctor=doctor,
            status__in=['pending', 'confirmed']
        ).order_by('date', 'start_time')
        
        # جلب المواعيد المؤكدة للاستشارات
        confirmed_appointments = Appointment.objects.filter(
            doctor=doctor,
            status='confirmed'
        ).select_related('patient').order_by('date', 'start_time')
        
        # جلب الاستشارات الحديثة للطبيب
        recent_consultations = Consultation.objects.filter(
            doctor=doctor
        ).select_related('patient').order_by('-date', '-start_time')[:5]
        
        # تعديل وقت الاستشارات (زيادة ساعة)
        for consultation in recent_consultations:
            consultation.start_time = (datetime.combine(datetime.today(), consultation.start_time) + timedelta(hours=1)).time()
            if consultation.end_time:
                consultation.end_time = (datetime.combine(datetime.today(), consultation.end_time) + timedelta(hours=1)).time()
        
        # حساب عدد الإشعارات غير المقروءة
        unread_count = notifications.count()
        
        return render(request, 'accounts/doctor_interface.html', {
            'doctor': doctor,
            'notifications': notifications,
            'pending_appointments': pending_appointments,
            'confirmed_appointments': confirmed_appointments,
            'recent_consultations': recent_consultations,
            'unread_count': unread_count,
            'is_doctor': True
        })
    except Doctor.DoesNotExist:
        messages.error(request, 'Profil médecin non trouvé. Veuillez vous reconnecter.')
        return redirect('doctor_login')

@login_required
def patient_interface(request):
    if not request.user.is_patient:
        messages.error(request, 'Accès non autorisé. Veuillez vous connecter en tant que patient.')
        return redirect('patient_login')
    
    try:
        patient = Patient.objects.get(user=request.user)
        # Get specialities from Doctor model
        specialities = Doctor.SPECIALITY_CHOICES
        
        # Get unread notifications for the patient
        notifications = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).order_by('-created_at')
        
        # تعديل وقت الإشعارات (إنقاص ساعة)
        for notification in notifications:
            notification.created_at = notification.created_at - timedelta(hours=1)
        
        # Get only pending and confirmed appointments
        appointments = Appointment.objects.filter(
            patient=patient,
            status__in=['pending', 'confirmed']
        ).order_by('date', 'start_time')

        # Get recent consultations for the patient
        recent_consultations = Consultation.objects.filter(
            patient=patient
        ).select_related('doctor').order_by('-date', '-start_time')[:5]
        
        # تعديل وقت الاستشارات (زيادة ساعة)
        for consultation in recent_consultations:
            consultation.start_time = (datetime.combine(datetime.today(), consultation.start_time) + timedelta(hours=1)).time()
            if consultation.end_time:
                consultation.end_time = (datetime.combine(datetime.today(), consultation.end_time) + timedelta(hours=1)).time()
        
        # Calculate unread notifications count
        unread_count = notifications.count()
        
        return render(request, 'accounts/patient_intface.html', {
            'patient': patient,
            'specialities': specialities,
            'notifications': notifications,
            'appointments': appointments,
            'recent_consultations': recent_consultations,
            'unread_count': unread_count,
            'is_doctor': False
        })
    except Patient.DoesNotExist:
        messages.error(request, 'Profil patient non trouvé. Veuillez vous reconnecter.')
        return redirect('patient_login')

@login_required
def consultation_room(request, consultation_id):
    print("=== Starting consultation_room view ===")
    print(f"User: {request.user.username}")
    print(f"Consultation ID: {consultation_id}")
    
    try:
        consultation_room = ConsultationRoom.objects.get(id=consultation_id)
        print(f"Found consultation room: {consultation_room.id}")
        print(f"Doctor: {consultation_room.doctor.user.username}")
        print(f"Patient: {consultation_room.patient.user.username}")
        
        # التحقق من أن المستخدم هو إما الطبيب أو المريض
        is_doctor = request.user == consultation_room.doctor.user
        is_patient = request.user == consultation_room.patient.user
        
        print(f"Is doctor: {is_doctor}")
        print(f"Is patient: {is_patient}")
        
        if not (is_doctor or is_patient):
            print("Unauthorized access attempt")
            messages.error(request, 'غير مصرح لك بالوصول إلى هذه الغرفة')
            return redirect('index')
        
        # تحديد الطرف الآخر
        other_party = consultation_room.patient if is_doctor else consultation_room.doctor
        print(f"Other party: {other_party.full_name}")
        
        context = {
            'consultation': consultation_room,
            'appointment': consultation_room.appointment,
            'other_party': other_party,
            'is_doctor': is_doctor,
            'user': request.user
        }
        
        print("Rendering consultation room template")
        return render(request, 'accounts/consultation_room.html', context)
        
    except ConsultationRoom.DoesNotExist:
        print(f"Consultation room {consultation_id} not found")
        messages.error(request, 'غرفة الاستشارة غير موجودة')
        return redirect('index')
    except Exception as e:
        print(f"Error in consultation_room view: {str(e)}")
        messages.error(request, f'حدث خطأ: {str(e)}')
        return redirect('index')

@login_required
def get_consultation_details(request, consultation_id):
    try:
        # جلب الاستشارة
        consultation = Consultation.objects.get(id=consultation_id)
        
        # التحقق من الصلاحيات - يجب أن يكون المستخدم إما الطبيب أو المريض
        if not (request.user == consultation.doctor.user or request.user == consultation.patient.user):
            return JsonResponse({
                'error': 'غير مصرح لك بالوصول إلى هذه المعلومات'
            }, status=403)
        
        # تحضير البيانات
        data = {
            'doctor_name': consultation.doctor_name,
            'patient_name': consultation.patient_name,
            'date': consultation.date.strftime('%d/%m/%Y'),
            'start_time': consultation.start_time.strftime('%H:%M'),
            'end_time': consultation.end_time.strftime('%H:%M') if consultation.end_time else '',
            'speciality': consultation.doctor.speciality,  # إضافة تخصص الطبيب
            'notes': consultation.notes
        }
        
        return JsonResponse(data)
        
    except Consultation.DoesNotExist:
        return JsonResponse({
            'error': 'الاستشارة غير موجودة'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'error': f'حدث خطأ: {str(e)}'
        }, status=500)

def admin_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # التحقق من أن المستخدم موجود وهو مسؤول
        try:
            user = CustomUser.objects.get(username=username)
            if user.is_superuser and user.check_password(password):
                login(request, user)
                return redirect('admin:index')  # توجيه إلى لوحة تحكم Django
            else:
                return render(request, 'accounts/admin-login.html', {
                    'error': 'Nom d\'utilisateur ou mot de passe incorrect'
                })
        except CustomUser.DoesNotExist:
            return render(request, 'accounts/admin-login.html', {
                'error': 'Nom d\'utilisateur ou mot de passe incorrect'
            })
    
    return render(request, 'accounts/admin-login.html')

@login_required
def admin_dashboard(request):
    if not request.user.is_superuser:
        messages.error(request, 'Accès non autorisé')
        return redirect('index')
    
    # إحصائيات النظام
    total_users = CustomUser.objects.count()
    total_doctors = Doctor.objects.count()
    total_patients = Patient.objects.count()
    today_appointments = Appointment.objects.filter(
        date=timezone.now().date()
    ).count()
    
    # المستخدمين الجدد
    recent_users = CustomUser.objects.order_by('-date_joined')[:10]
    
    # المواعيد الحديثة
    recent_appointments = Appointment.objects.order_by('-created_at')[:10]
    
    context = {
        'total_users': total_users,
        'total_doctors': total_doctors,
        'total_patients': total_patients,
        'today_appointments': today_appointments,
        'recent_users': recent_users,
        'recent_appointments': recent_appointments,
    }
    
    return render(request, 'accounts/admin_dashboard.html', context)

@login_required
def logout_view(request):
    # حفظ نوع المستخدم قبل تسجيل الخروج
    is_doctor = request.user.is_doctor
    
    # تسجيل الخروج
    logout(request)
    
    # إضافة رسالة نجاح
    messages.success(request, 'Vous avez été déconnecté avec succès')
    
    # توجيه المستخدم إلى صفحة تسجيل الدخول المناسبة
    if is_doctor:
        return redirect('doctor_login')
    else:
        return redirect('patient_login')

