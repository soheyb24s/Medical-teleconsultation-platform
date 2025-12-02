from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
import json
from datetime import datetime, timedelta, time
from .models import Doctor, DoctorAvailability, Appointment, Notification, Patient, ConsultationRoom, Consultation
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

@login_required
@require_http_methods(["GET"])
def get_available_slots(request):
    try:
        date_str = request.GET.get('date')
        doctor_id = request.GET.get('doctor_id')
        
        if not date_str or not doctor_id:
            return JsonResponse({'error': 'Date and doctor_id parameters are required'}, status=400)
        
        # Convert string date to datetime object
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Check if the requested date is today
        today = datetime.now().date()
        if date <= today:
            return JsonResponse({
                'success': True,
                'available_slots': [],
                'message': 'Les rendez-vous ne peuvent être pris qu\'à partir de demain'
            })
        
        # Get the doctor's availability for the specified date
        availabilities = DoctorAvailability.objects.filter(
            doctor_id=doctor_id,
            date=date,
            is_available=True
        )

        available_slots = []
        for availability in availabilities:
            available_slots.append({
                'time': availability.start_time.strftime('%H:%M'),
                'end_time': availability.end_time.strftime('%H:%M')
            })

        return JsonResponse({
            'success': True,
            'available_slots': available_slots
        })

    except ObjectDoesNotExist:
        return JsonResponse({
            'error': 'Doctor not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)

@login_required
@require_http_methods(["POST"])
@csrf_exempt
def book_appointment(request):
    try:
        data = json.loads(request.body)
        doctor_id = data.get('doctor_id')
        date_str = data.get('date')
        time_str = data.get('time')
        notes = data.get('notes', '')
        
        if not all([doctor_id, date_str, time_str]):
            return JsonResponse({
                'success': False,
                'message': 'Tous les champs sont obligatoires'
            }, status=400)

        # تحويل التاريخ والوقت
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        start_time = datetime.strptime(time_str, '%H:%M').time()
        
        # التحقق من توفر الموعد
        try:
            doctor = Doctor.objects.get(id=doctor_id)
            availability = DoctorAvailability.objects.get(
                doctor_id=doctor_id,
                date=date,
                start_time=start_time,
                is_available=True
            )
            
            # الحصول على المريض
            try:
                patient = Patient.objects.get(user=request.user)
            except Patient.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Patient non trouvé'
                }, status=404)
                
        except Doctor.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Médecin non trouvé'
            }, status=404)
        except DoctorAvailability.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Ce créneau horaire n\'est plus disponible'
            }, status=404)

        # حساب وقت النهاية (30 دقيقة بعد وقت البداية)
        end_time = (datetime.combine(datetime.today(), start_time) + timedelta(minutes=30)).time()
        
        # إنشاء الموعد
        appointment = Appointment.objects.create(
            doctor=doctor,
            patient=patient,
            date=date,
            start_time=start_time,
            end_time=end_time,
            status='pending',
            notes=notes
        )
        
        # تحديث حالة الوقت المتاح
        availability.is_available = False
        availability.save()

        # إنشاء إشعار للطبيب
        Notification.objects.create(
            recipient=doctor.user,
            type='appointment_created',
            message=f'Nouveau rendez-vous avec {patient.full_name} le {date} à {start_time}',
            appointment=appointment
        )

        return JsonResponse({
            'success': True,
            'message': 'Rendez-vous créé avec succès',
            'appointment': {
                'id': appointment.id,
                'doctor_name': doctor.full_name,
                'date': date.strftime('%Y-%m-%d'),
                'time': start_time.strftime('%H:%M'),
                'status': appointment.status
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Données invalides'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Une erreur est survenue: {str(e)}'
        }, status=500)

@login_required
@require_http_methods(["POST"])
@csrf_exempt
def cancel_appointment(request):
    try:
        print("=== Début de la fonction cancel_appointment ===")
        print(f"Utilisateur: {request.user.username}, ID: {request.user.id}")
        
        data = json.loads(request.body)
        appointment_id = data.get('appointment_id')
        
        if not appointment_id:
            return JsonResponse({
                'success': False,
                'message': 'ID du rendez-vous requis'
            }, status=400)

        with transaction.atomic():
            # Get the appointment
            appointment = Appointment.objects.select_for_update().get(id=appointment_id)
            
            # Verify that the user is either the patient or the doctor
            if request.user != appointment.patient.user and request.user != appointment.doctor.user:
                return JsonResponse({
                    'success': False,
                    'message': 'Vous n\'êtes pas autorisé à annuler ce rendez-vous'
                }, status=403)

            # If the patient is cancelling and the appointment is still pending
            if request.user == appointment.patient.user and appointment.status == 'pending':
                # Delete the appointment creation notification sent to the doctor
                Notification.objects.filter(
                    recipient=appointment.doctor.user,
                    type='appointment_created',
                    appointment=appointment
                ).delete()

            # Update appointment status to cancelled
            appointment.status = 'cancelled'
            appointment.save()

            # Make the time slot available again
            availability, created = DoctorAvailability.objects.get_or_create(
                doctor=appointment.doctor,
                date=appointment.date,
                start_time=appointment.start_time,
                end_time=appointment.end_time,
                defaults={'is_available': True}
            )
            if not created:
                availability.is_available = True
                availability.save()

            # Create notifications for both parties
            if request.user == appointment.patient.user:
                # If patient cancelled, notify doctor with patient's name
                notification_message = f'Rendez-vous annulé par {appointment.patient.full_name}  le {appointment.date.strftime("%d/%m/%Y")} à {appointment.start_time.strftime("%H:%M")}'
                Notification.objects.create(
                    recipient=appointment.doctor.user,
                    type='appointment_cancelled',
                    message=notification_message,
                    appointment=appointment
                )
            else:
                # If doctor cancelled, notify patient with doctor's name
                notification_message = f'Rendez-vous annulé par Dr. {appointment.doctor.full_name}  le {appointment.date.strftime("%d/%m/%Y")} à {appointment.start_time.strftime("%H:%M")}'
                Notification.objects.create(
                    recipient=appointment.patient.user,
                    type='appointment_cancelled',
                    message=notification_message,
                    appointment=appointment
                )

            return JsonResponse({
                'success': True,
                'message': 'Rendez-vous annulé avec succès'
            })

    except Appointment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Rendez-vous non trouvé'
        }, status=404)
    except Exception as e:
        print(f"Erreur dans cancel_appointment: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'Une erreur est survenue: {str(e)}'
        }, status=500)

@require_http_methods(["POST"])
@csrf_exempt
@login_required
def update_doctor_availability(request):
    try:
        data = json.loads(request.body)
        date_str = data.get('date')
        time_slots = data.get('time_slots', [])
        
        # تحويل التاريخ من نص إلى كائن تاريخ
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # التحقق من أن التاريخ المحدد ليس اليوم الحالي أو تاريخ سابق
        today = datetime.now().date()
        if selected_date <= today:
            return JsonResponse({
                'success': False,
                'message': 'Impossible d\'ajouter des créneaux pour aujourd\'hui ou une date passée. Veuillez choisir une date à partir de demain.'
            }, status=400)
        
        # التحقق من وجود الطبيب
        try:
            doctor = Doctor.objects.get(user=request.user)
        except Doctor.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Médecin non trouvé'
            }, status=404)
        
        # حذف الأوقات المتاحة السابقة لهذا التاريخ
        DoctorAvailability.objects.filter(doctor=doctor, date=selected_date).delete()
        
        # إنشاء قائمة من الأوقات المتاحة الجديدة
        availabilities = []
        for time_slot in time_slots:
            start_time = datetime.strptime(time_slot, '%H:%M').time()
            # حساب وقت النهاية (30 دقيقة بعد وقت البداية)
            end_time = (datetime.combine(datetime.today(), start_time) + timedelta(minutes=30)).time()
            
            availability = DoctorAvailability(
                doctor=doctor,
                doctor_name=doctor.full_name,
                doctor_email=doctor.email,
                date=selected_date,
                start_time=start_time,
                end_time=end_time,
                is_available=True
            )
            availabilities.append(availability)
        
        # حفظ جميع الأوقات المتاحة دفعة واحدة
        DoctorAvailability.objects.bulk_create(availabilities)
        
        return JsonResponse({
            'success': True,
            'message': 'Les créneaux horaires ont été mis à jour avec succès',
            'availabilities': [
                {
                    'date': selected_date.strftime('%Y-%m-%d'),
                    'doctor_name': doctor.full_name,
                    'doctor_email': doctor.email,
                    'start_time': slot.start_time.strftime('%H:%M'),
                    'end_time': slot.end_time.strftime('%H:%M')
                }
                for slot in availabilities
            ]
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Données invalides'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)

@login_required
def delete_doctor_availability(request):
    if request.method == 'POST':
        try:
            doctor = Doctor.objects.get(user=request.user)
            DoctorAvailability.objects.filter(doctor=doctor).delete()
            return JsonResponse({
                'status': 'success',
                'message': 'Toutes les disponibilités ont été supprimées avec succès'
            })
        except Doctor.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Médecin non trouvé'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    return JsonResponse({
        'status': 'error',
        'message': 'Méthode non autorisée'
    }, status=405)

@login_required
@require_http_methods(["GET"])
def get_doctors_by_speciality(request):
    try:
        speciality = request.GET.get('speciality')
        if not speciality:
            return JsonResponse({'error': 'Speciality parameter is required'}, status=400)
        
        doctors = Doctor.objects.filter(speciality=speciality, is_verified=True)
        doctors_list = [{
            'id': doctor.id,
            'full_name': doctor.full_name,
            'speciality': doctor.speciality,
            'email': doctor.email
        } for doctor in doctors]
        
        return JsonResponse({
            'success': True,
            'doctors': doctors_list
        })
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)

@login_required
@require_http_methods(["GET"])
def get_available_dates(request):
    try:
        doctor_id = request.GET.get('doctor_id')
        month = request.GET.get('month')  # Get the selected month
        year = request.GET.get('year')    # Get the selected year
        
        if not doctor_id:
            return JsonResponse({'error': 'Doctor ID is required'}, status=400)
        
        # Get today's date
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        # If month and year are provided, use them to filter dates
        if month and year:
            # Convert month and year to integers
            month = int(month)
            year = int(year)
            
            # Create start and end dates for the selected month
            start_date = max(datetime(year, month, 1).date(), tomorrow)
            # Calculate the last day of the month
            if month == 12:
                end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
            else:
                end_date = datetime(year, month + 1, 1).date() - timedelta(days=1)
        else:
            # Default to current month if not specified
            start_date = tomorrow
            if today.month == 12:
                end_date = datetime(today.year + 1, 1, 1).date() - timedelta(days=1)
            else:
                end_date = datetime(today.year, today.month + 1, 1).date() - timedelta(days=1)
        
        # Get all available slots from DoctorAvailability for the selected month
        availabilities = DoctorAvailability.objects.filter(
            doctor_id=doctor_id,
            date__gte=start_date,
            date__lte=end_date,
            is_available=True
        ).order_by('date')
        
        # Get all appointments for this doctor in the date range
        appointments = Appointment.objects.filter(
            doctor_id=doctor_id,
            date__gte=start_date,
            date__lte=end_date,
            status__in=['pending', 'confirmed']
        ).values_list('date', 'start_time')
        
        # Create a dictionary of dates with their available time slots
        available_dates_dict = {}
        
        # Process availabilities
        for availability in availabilities:
            date_str = availability.date.strftime('%Y-%m-%d')
            time_slot = availability.start_time.strftime('%H:%M')
            
            # Check if this time slot is already booked
            is_booked = any(date == availability.date and time == availability.start_time 
                           for date, time in appointments)
            
            if not is_booked:
                if date_str not in available_dates_dict:
                    available_dates_dict[date_str] = []
                available_dates_dict[date_str].append(time_slot)
        
        # Convert to list of dates
        available_dates = list(available_dates_dict.keys())
        
        # Debug information
        print(f"Doctor ID: {doctor_id}")
        print(f"Month: {month}, Year: {year}")
        print(f"Start date: {start_date}, End date: {end_date}")
        print(f"Available dates: {available_dates}")
        print(f"Total availabilities found: {availabilities.count()}")
        
        return JsonResponse({
            'success': True,
            'available_dates': available_dates
        })
    except Exception as e:
        print(f"Error in get_available_dates: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=500)

@login_required
@require_http_methods(["POST"])
@csrf_exempt
def accept_appointment(request):
    try:
        data = json.loads(request.body)
        appointment_id = data.get('appointment_id')
        notification_id = data.get('notification_id')

        if not appointment_id or not notification_id:
            return JsonResponse({
                'success': False,
                'message': 'Missing required fields'
            }, status=400)

        appointment = Appointment.objects.get(id=appointment_id)
        notification = Notification.objects.get(id=notification_id)

        # تحديث حالة الموعد
        appointment.status = 'confirmed'
        appointment.save()

        # تحديث حالة الإشعار الأصلي
        notification.is_read = True
        notification.save()

        # إنشاء إشعار للمريض
        Notification.objects.create(
            recipient=appointment.patient.user,
            sender=appointment.doctor.user,
            type='appointment_accepted',
            message=f'Votre rendez-vous avec Dr. {appointment.doctor.full_name} le {appointment.date.strftime("%d/%m/%Y")} à {appointment.start_time.strftime("%H:%M")} a été accepté',
            appointment=appointment
        )

        return JsonResponse({
            'success': True,
            'message': 'Rendez-vous accepté avec succès',
            'appointment': {
                'id': appointment.id,
                'doctor_name': appointment.doctor.full_name,
                'date': appointment.date.strftime('%Y-%m-%d'),
                'time': appointment.start_time.strftime('%H:%M'),
                'status': appointment.status
            },
            'notification_id': notification_id
        })

    except Appointment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'الموعد غير موجود'
        }, status=404)
    except Notification.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'الإشعار غير موجود'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)

@login_required
@require_http_methods(["POST"])
@csrf_exempt
def refuse_appointment(request):
    try:
        data = json.loads(request.body)
        appointment_id = data.get('appointment_id')
        notification_id = data.get('notification_id')
        reason = data.get('reason', 'تم رفض الموعد من قبل الطبيب')

        if not appointment_id or not notification_id:
            return JsonResponse({
                'success': False,
                'message': 'Missing required fields'
            }, status=400)

        appointment = Appointment.objects.get(id=appointment_id)
        notification = Notification.objects.get(id=notification_id)

        # Make the time slot available again
        availability, created = DoctorAvailability.objects.get_or_create(
            doctor=appointment.doctor,
            date=appointment.date,
            start_time=appointment.start_time,
            end_time=appointment.end_time,
            defaults={
                'is_available': True,
                'doctor_name': appointment.doctor.full_name,
                'doctor_email': appointment.doctor.email
            }
        )
        
        if not created:
            availability.is_available = True
            availability.save()

        # تحديث حالة الموعد
        appointment.status = 'refused'
        appointment.save()

        # تحديث حالة الإشعار الأصلي
        notification.is_read = True
        notification.save()

        # إنشاء إشعار للمريض
        Notification.objects.create(
            recipient=appointment.patient.user,
            type='appointment_refused',
            message=f'Votre rendez-vous avec Dr. {appointment.doctor.full_name} le {appointment.date.strftime("%d/%m/%Y")} à {appointment.start_time.strftime("%H:%M")} a été refusé'
        )

        return JsonResponse({
            'success': True,
            'message': 'Rendez-vous refusé avec succès',
            'appointment': {
                'id': appointment.id,
                'doctor_name': appointment.doctor.full_name,
                'date': appointment.date.strftime('%Y-%m-%d'),
                'time': appointment.start_time.strftime('%H:%M'),
                'status': appointment.status
            },
            'notification_id': notification_id
        })

    except Appointment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'الموعد غير موجود'
        }, status=404)
    except Notification.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'الإشعار غير موجود'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)

@login_required
@require_http_methods(["POST"])
@csrf_exempt
def mark_notification_read(request):
    try:
        print("Début de la fonction mark_notification_read")
        print(f"Utilisateur: {request.user.username}, ID: {request.user.id}")
        print(f"Corps de la requête: {request.body}")
        
        try:
            data = json.loads(request.body)
            print(f"Données JSON décodées: {data}")
        except json.JSONDecodeError as e:
            print(f"Erreur de décodage JSON: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': 'Invalid JSON data'
            }, status=400)
            
        notification_id = data.get('notification_id')
        print(f"Notification ID reçu: {notification_id}")
        
        if not notification_id:
            print("Erreur: Notification ID manquant")
            return JsonResponse({
                'success': False,
                'message': 'Notification ID is required'
            }, status=400)

        # Get the notification and verify ownership
        try:
            notification = Notification.objects.get(id=notification_id, recipient=request.user)
            print(f"Notification trouvée: {notification.id}, is_read: {notification.is_read}")
        except Notification.DoesNotExist:
            print(f"Notification non trouvée avec ID: {notification_id}")
            return JsonResponse({
                'success': False,
                'message': 'Notification not found'
            }, status=404)
        
        # Mark as read
        notification.is_read = True
        notification.save()
        print(f"Notification marquée comme lue: {notification.id}")
        
        # Get updated unread count
        unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        print(f"Nouveau nombre de notifications non lues: {unread_count}")
        
        return JsonResponse({
            'success': True,
            'message': 'Notification marked as read',
            'unread_count': unread_count
        })

    except Exception as e:
        print(f"Erreur inattendue: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)

@login_required
@require_http_methods(["POST"])
@csrf_exempt
def confirm_consultation(request):
    try:
        print("=== Starting confirm_consultation ===")
        print(f"User: {request.user.username}")
        
        data = json.loads(request.body)
        appointment_id = data.get('appointment_id')
        print(f"Appointment ID: {appointment_id}")
        
        if not appointment_id:
            return JsonResponse({
                'success': False,
                'message': 'معرف الموعد مطلوب'
            }, status=400)

        appointment = Appointment.objects.get(id=appointment_id)
        print(f"Found appointment: {appointment.id}")
        print(f"Current status - Doctor confirmed: {appointment.doctor_confirmed}, Patient confirmed: {appointment.patient_confirmed}")
        
        # التحقق من أن المستخدم هو إما الطبيب أو المريض
        if request.user != appointment.doctor.user and request.user != appointment.patient.user:
            print("Unauthorized user tried to confirm consultation")
            return JsonResponse({
                'success': False,
                'message': 'غير مصرح لك بتأكيد هذا الموعد'
            }, status=403)

        # تحديث حالة التأكيد
        if request.user == appointment.doctor.user:
            print("Doctor confirming consultation")
            appointment.doctor_confirmed = True
        else:
            print("Patient confirming consultation")
            appointment.patient_confirmed = True
            
        # إذا أكد كلا الطرفين، قم بتحديث حالة الموعد وإنشاء غرفة الاستشارة
        if appointment.doctor_confirmed and appointment.patient_confirmed:
            print("Both parties confirmed - creating consultation room")
            try:
                appointment.status = 'in_progress'
                
                # التحقق من عدم وجود غرفة استشارة سابقة
                existing_room = ConsultationRoom.objects.filter(appointment=appointment).first()
                if existing_room:
                    print(f"Found existing consultation room: {existing_room.id}")
                    consultation_room = existing_room
                else:
                    print("Creating new consultation room")
                    consultation_room = ConsultationRoom.objects.create(
                        appointment=appointment,
                        doctor=appointment.doctor,
                        patient=appointment.patient
                    )
                    print(f"Created new consultation room: {consultation_room.id}")
                
                appointment.save()
                
                redirect_url = f'/consultation/{consultation_room.id}/'
                print(f"Redirecting to: {redirect_url}")
                
                return JsonResponse({
                    'success': True,
                    'message': 'تم بدء الاستشارة بنجاح',
                    'redirect_url': redirect_url
                })
            except Exception as e:
                print(f"Error creating consultation room: {str(e)}")
                return JsonResponse({
                    'success': False,
                    'message': f'حدث خطأ أثناء إنشاء غرفة الاستشارة: {str(e)}'
                }, status=500)
        else:
            print("One party confirmed - saving and notifying other party")
            # إذا أكد طرف واحد فقط، قم بحفظ الموعد وإرسال إشعار للطرف الآخر
            appointment.save()
            
            # Create notification for the other party
            other_party = appointment.patient.user if request.user == appointment.doctor.user else appointment.doctor.user
            if request.user == appointment.doctor.user:
                # If doctor confirmed, notify patient with doctor's name
                notification_message = f'Dr. {appointment.doctor.full_name} a confirmé la consultation  prévue le {appointment.date.strftime("%d/%m/%Y")} à {appointment.start_time.strftime("%H:%M")}'
            else:
                # If patient confirmed, notify doctor with patient's name
                notification_message = f'{appointment.patient.full_name} a confirmé la consultation  prévue le {appointment.date.strftime("%d/%m/%Y")} à {appointment.start_time.strftime("%H:%M")}'
            
            Notification.objects.create(
                recipient=other_party,
                type='consultation_joined',
                message=notification_message,
                appointment=appointment
            )
            
            return JsonResponse({
                'success': True,
                'message': 'تم تأكيد الاستشارة بنجاح',
                'status': {
                    'doctor_confirmed': appointment.doctor_confirmed,
                    'patient_confirmed': appointment.patient_confirmed
                }
            })

    except Appointment.DoesNotExist:
        print(f"Appointment {appointment_id} not found")
        return JsonResponse({
            'success': False,
            'message': 'الموعد غير موجود'
        }, status=404)
    except Exception as e:
        print(f"Error in confirm_consultation: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)

@login_required
@require_http_methods(["GET"])
def check_consultation_status(request):
    try:
        appointment_id = request.GET.get('appointment_id')
        
        if not appointment_id:
            return JsonResponse({
                'success': False,
                'message': 'معرف الموعد مطلوب'
            }, status=400)

        appointment = Appointment.objects.get(id=appointment_id)
        
        # التحقق من أن المستخدم هو إما الطبيب أو المريض
        if request.user != appointment.doctor.user and request.user != appointment.patient.user:
            return JsonResponse({
                'success': False,
                'message': 'غير مصرح لك بالوصول إلى حالة هذا الموعد'
            }, status=403)

        # التحقق من وجود غرفة استشارة
        try:
            consultation_room = ConsultationRoom.objects.get(appointment=appointment)
            return JsonResponse({
                'success': True,
                'status': {
                    'doctor_confirmed': appointment.doctor_confirmed,
                    'patient_confirmed': appointment.patient_confirmed,
                    'consultation_room': {
                        'id': consultation_room.id,
                        'url': f'/consultation/{consultation_room.id}/'
                    }
                }
            })
        except ConsultationRoom.DoesNotExist:
            return JsonResponse({
                'success': True,
                'status': {
                    'doctor_confirmed': appointment.doctor_confirmed,
                    'patient_confirmed': appointment.patient_confirmed
                }
            })

    except Appointment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'الموعد غير موجود'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)

@login_required
@require_http_methods(["POST"])
@csrf_exempt
def end_consultation(request):
    try:
        print("=== Starting end_consultation ===")
        print(f"User: {request.user.username}")
        
        data = json.loads(request.body)
        consultation_id = data.get('consultation_id')
        
        if not consultation_id:
            return JsonResponse({
                'success': False,
                'message': 'Consultation ID is required'
            }, status=400)

        # Get the consultation room
        consultation_room = ConsultationRoom.objects.get(id=consultation_id)
        
        # Check if user is authorized
        if request.user != consultation_room.doctor.user and request.user != consultation_room.patient.user:
            return JsonResponse({
                'success': False,
                'message': 'Unauthorized to end this consultation'
            }, status=403)
        
        # Update consultation room status
        consultation_room.end_time = timezone.now()
        consultation_room.is_active = False
        consultation_room.save()
        
        # Update appointment status
        appointment = consultation_room.appointment
        appointment.status = 'completed'
        appointment.save()

        # Create consultation record
        consultation = Consultation.objects.create(
            appointment=appointment,
            doctor=consultation_room.doctor,
            patient=consultation_room.patient,
            doctor_name=consultation_room.doctor.full_name,
            patient_name=consultation_room.patient.full_name,
            date=appointment.date,
            start_time=consultation_room.created_at.time(),
            end_time=consultation_room.end_time.time(),
            notes=f"Consultation de {consultation_room.doctor.speciality} avec Dr. {consultation_room.doctor.full_name}"
        )
        
        print(f"Successfully created consultation record: {consultation.id}")
        print(f"Start time: {consultation.start_time}")
        print(f"End time: {consultation.end_time}")
        print(f"Specialty: {consultation_room.doctor.speciality}")
        
        return JsonResponse({
            'success': True,
            'message': 'Consultation ended and recorded successfully'
        })

    except ConsultationRoom.DoesNotExist:
        print(f"Consultation room {consultation_id} not found")
        return JsonResponse({
            'success': False,
            'message': 'Consultation room not found'
        }, status=404)
    except Exception as e:
        print(f"Error in end_consultation: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=500)

# Add these imports at the top if not already present
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

@login_required
@require_http_methods(["POST"])
@csrf_exempt
def update_profile(request):
    try:
        data = json.loads(request.body)
        
        # Get the user type and corresponding profile
        if request.user.is_doctor:
            profile = Doctor.objects.get(user=request.user)
        else:
            profile = Patient.objects.get(user=request.user)

        # Update common fields
        if 'full_name' in data:
            profile.full_name = data['full_name']
        
        if 'email' in data:
            try:
                validate_email(data['email'])
                # Update both user and profile email
                request.user.email = data['email']
                request.user.username = data['email']  # Since we use email as username
                profile.email = data['email']
            except ValidationError:
                return JsonResponse({
                    'success': False,
                    'message': 'Email invalide'
                }, status=400)

        # Update password if provided
        if 'new_password' in data and data['new_password']:
            if not data.get('current_password'):
                return JsonResponse({
                    'success': False,
                    'message': 'Le mot de passe actuel est requis'
                }, status=400)

            # Verify current password
            if not request.user.check_password(data['current_password']):
                return JsonResponse({
                    'success': False,
                    'message': 'Mot de passe actuel incorrect'
                }, status=400)

            # Update password
            request.user.set_password(data['new_password'])
            profile.password = request.user.password
            password_changed = True

        # Update doctor-specific fields
        if request.user.is_doctor:
            if 'speciality' in data:
                profile.speciality = data['speciality']

        # Save changes
        with transaction.atomic():
            request.user.save()
            profile.save()

        return JsonResponse({
            'success': True,
            'message': 'Profil mis à jour avec succès',
            'password_changed': password_changed if 'password_changed' in locals() else False
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Données invalides'
        }, status=400)
    except (Doctor.DoesNotExist, Patient.DoesNotExist):
        return JsonResponse({
            'success': False,
            'message': 'Profil non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)