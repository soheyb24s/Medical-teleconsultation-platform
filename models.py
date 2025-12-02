from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

class CustomUser(AbstractUser):
    is_patient = models.BooleanField(default=False)
    is_doctor = models.BooleanField(default=False)

class Patient(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128, default='')  # إضافة قيمة افتراضية
    date_joined = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return self.full_name
    
    class Meta:
        db_table = 'patient'

class LicenseNumber(models.Model):
    number = models.CharField(max_length=50, unique=True)
    is_valid = models.BooleanField(default=True)
    
    def __str__(self):
        return self.number
    
    class Meta:
        db_table = 'license_number'

class Doctor(models.Model):
    SPECIALITY_CHOICES = [
        ('Médecine Général', 'Médecine Général'),
        ('Cardiologie', 'Cardiologie'),
        ('Neurologie', 'Neurologie'),
        ('Dentiste', 'Dentiste'),
        ('Ophtalmologie', 'Ophtalmologie'),
        ('Orthopédie', 'Orthopédie'),
    ]

    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128, default='')
    license_number = models.CharField(max_length=50, unique=True)
    date_joined = models.DateTimeField(default=timezone.now)
    is_verified = models.BooleanField(default=False)
    speciality = models.CharField(max_length=20, choices=SPECIALITY_CHOICES, null=False, blank=False)
    
    def __str__(self):
        return self.full_name
    
    def save(self, *args, **kwargs):
        # التحقق من أن التخصص موجود
        if not self.speciality:
            raise ValueError("Speciality is required")
            
        # التحقق من أن القيمة موجودة في القائمة
        valid_choices = [choice[0] for choice in self.SPECIALITY_CHOICES]
        if self.speciality not in valid_choices:
            raise ValueError(f"Invalid speciality value. Must be one of: {', '.join(valid_choices)}")
            
        super().save(*args, **kwargs)
    
    class Meta:
        db_table = 'medcin'

class DoctorAvailability(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='availabilities')
    doctor_name = models.CharField(max_length=100, null=True, blank=True)
    doctor_email = models.EmailField(null=True, blank=True)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'disponibilite_medcin'
        ordering = ['date', 'start_time']
        unique_together = ['doctor', 'date', 'start_time', 'end_time']

    def save(self, *args, **kwargs):
        if not self.doctor_name:
            self.doctor_name = self.doctor.full_name
        if not self.doctor_email:
            self.doctor_email = self.doctor.email
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.doctor_name} - {self.date} ({self.start_time}-{self.end_time})"

class Appointment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('confirmed', 'Confirmé'),
        ('refused', 'Refusé'),
        ('in_progress', 'En cours'),
        ('cancelled', 'Annulé'),
        ('completed', 'Terminé')
    ]

    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='appointments')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='appointments')
    doctor_name = models.CharField(max_length=100)
    patient_name = models.CharField(max_length=100)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    doctor_confirmed = models.BooleanField(default=False)
    patient_confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'rendez_vous'
        ordering = ['-date', '-start_time']

    def save(self, *args, **kwargs):
        if not self.doctor_name:
            self.doctor_name = self.doctor.full_name
        if not self.patient_name:
            self.patient_name = self.patient.full_name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.patient_name} avec Dr. {self.doctor_name} - {self.date} {self.start_time}"

class Notification(models.Model):
    TYPE_CHOICES = [
        ('appointment_created', 'Rendez-vous créé'),
        ('appointment_accepted', 'Rendez-vous accepté'),
        ('appointment_refused', 'Rendez-vous refusé'),
        ('appointment_cancelled', 'Rendez-vous annulé'),
        ('consultation_joined', 'Consultation joignée')
        
    ]

    recipient = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sent_notifications', null=True, blank=True)
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        db_table = 'notification'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.recipient.username} - {self.type} - {self.created_at}"

class Consultation(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='consultation')
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='consultations')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='consultations')
    doctor_name = models.CharField(max_length=100)
    patient_name = models.CharField(max_length=100)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    notes = models.TextField(blank=True, null=True)
    diagnosis = models.TextField(blank=True, null=True)
    prescription = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'consultation'
        ordering = ['-date', '-start_time']

    def save(self, *args, **kwargs):
        if not self.doctor_name:
            self.doctor_name = self.doctor.full_name
        if not self.patient_name:
            self.patient_name = self.patient.full_name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Consultation: {self.patient_name} avec Dr. {self.doctor_name} - {self.date} {self.start_time}"

class ConsultationRoom(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='consultation_room')
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='consultation_rooms')
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='consultation_rooms')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'consultation_room'
        ordering = ['-created_at']

    def __str__(self):
        return f"Consultation Room: {self.appointment.doctor.full_name} - {self.appointment.patient.full_name}"

class ConsultationMessage(models.Model):
    MESSAGE_TYPES = [
        ('text', 'Message texte'),
        ('image', 'Image'),
        ('document', 'Document')
    ]

    consultation_room = models.ForeignKey(ConsultationRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='received_messages', null=True)
    sender_name = models.CharField(max_length=100, null=True, blank=True)
    recipient_name = models.CharField(max_length=100, null=True, blank=True)
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES)
    content = models.TextField(null=True, blank=True)  # Pour les messages texte
    file = models.FileField(upload_to='consultation_files/%Y/%m/%d/', null=True, blank=True)  # Pour les fichiers et images
    file_name = models.CharField(max_length=255, null=True, blank=True)
    file_size = models.IntegerField(null=True, blank=True)  # Taille en octets
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        db_table = 'consultation_message'
        ordering = ['created_at']

    def __str__(self):
        sender_full_name = self.get_sender_full_name()
        recipient_full_name = self.get_recipient_full_name()
        
        if self.message_type == 'text':
            return f"Message de {sender_full_name} à {recipient_full_name}"
        else:
            return f"{self.get_message_type_display()} de {sender_full_name} à {recipient_full_name}"

    def get_sender_full_name(self):
        if self.sender_name:
            return self.sender_name
        if hasattr(self.sender, 'doctor'):
            return self.sender.doctor.full_name
        if hasattr(self.sender, 'patient'):
            return self.sender.patient.full_name
        return self.sender.username

    def get_recipient_full_name(self):
        if not self.recipient:
            return "tous"
        if self.recipient_name:
            return self.recipient_name
        if hasattr(self.recipient, 'doctor'):
            return self.recipient.doctor.full_name
        if hasattr(self.recipient, 'patient'):
            return self.recipient.patient.full_name
        return self.recipient.username

    def save(self, *args, **kwargs):
        # Set sender name
        if not self.sender_name:
            self.sender_name = self.get_sender_full_name()
        
        # Set recipient name
        if self.recipient and not self.recipient_name:
            self.recipient_name = self.get_recipient_full_name()

        if self.file and not self.file_name:
            self.file_name = self.file.name
        if self.file and not self.file_size:
            self.file_size = self.file.size
        super().save(*args, **kwargs)
