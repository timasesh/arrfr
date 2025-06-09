from django.urls import path
from . import views

urlpatterns = [
    # Authentication URLs
    path('', views.login_view, name='login_view'),
    path('logout/', views.logout_view, name='logout'),
    path('aadminpanell/', views.admin_page, name='admin_page'),  # Новый URL для админ-панели

    # Main Pages
    path('student_page/', views.student_page, name='student_page'),
    path('profile/', views.student_profile, name='student_profile'),
    path('students/<int:user_id>/', views.student_details, name='student_details'),
    path('success/', views.success_view, name='success'),

    # User Management
    path('delete_user/<int:user_id>/', views.delete_user, name='delete_user'),
    path('delete_student/<int:user_id>/', views.delete_user, name='delete_student'),  # Alias for delete_user

    # Course Management
    path('course/<int:course_id>/', views.course_detail, name='course_detail'),
    path('delete_course/<int:course_id>/', views.delete_course, name='delete_course'),
    path('create_course/', views.create_course, name='create_course'),
    path('add_module_to_course/<int:course_id>/', views.add_module_to_course, name='add_module_to_course'),
    path('detach_course/<int:user_id>/<int:course_id>/', views.detach_course, name='detach_course'),
    path('remove_course/<int:course_id>/', views.remove_course_from_student, name='remove_course_from_student'),

    # Module Management
    path('module/details/<int:module_id>/', views.module_details, name='module_details'),
    path('delete/module/<int:module_id>/', views.delete_module, name='delete_module'),
    path('create_module/', views.create_module, name='create_module'),
    path('create_module/<int:module_id>/', views.create_module, name='create_module_with_id'),
    path('detach_module/<int:course_id>/<int:module_id>/', views.detach_module, name='detach_module'),

    # Lesson Management
    path('create_lesson/', views.create_lesson, name='create_lesson'),
    path('create_lesson/<int:module_id>/', views.create_lesson, name='create_lesson_with_module'),
    path('delete/lesson/<int:lesson_id>/', views.delete_lesson, name='delete_lesson'),
    path('lesson/<int:lesson_id>/', views.view_lesson, name='view_lesson'),
    path('replace-video/<int:lesson_id>/', views.replace_video, name='replace_video'),
    path('replace-pdf/<int:lesson_id>/', views.replace_pdf, name='replace_pdf'),
    path('detach-lesson/<int:lesson_id>/from-module/<int:module_id>/', views.detach_lesson_from_module, name='detach_lesson_from_module'),
    path('edit_lesson/<int:lesson_id>/', views.edit_lesson, name='edit_lesson'),
    path('lesson_content/<int:lesson_id>/', views.get_lesson_content, name='get_lesson_content'), # URL для AJAX запроса контента урока

    # Quiz Management
    path('quizzes/', views.quiz_list, name='quiz_list'),
    path('create/quiz/', views.create_quiz, name='create_quiz'),
    path('edit/quiz/<int:pk>/', views.edit_quiz, name='edit_quiz'),
    path('quiz/<int:quiz_id>/', views.quiz_detail, name='quiz_detail'),
    path('quiz/<int:quiz_id>/start/', views.start_quiz, name='start_quiz'),
    path('quiz/<int:quiz_id>/result/', views.quiz_result, name='quiz_result'),
    path('delete/quiz/<int:quiz_id>/', views.delete_quiz, name='delete_quiz'),
    path('quiz/<int:quiz_id>/add-question/', views.add_question, name='add_question'),
    path('bind_quiz_to_module/<int:quiz_id>/', views.bind_quiz_to_module, name='bind_quiz_to_module'),

    # Progress Tracking
    path('update_progress/', views.update_progress, name='update_progress'),

    # New URL for adding a lesson to a module
    path('add-lesson-to-module/<int:module_id>/', views.add_lesson_to_module, name='add_lesson_to_module'),

    # New URL for editing answers via AJAX
    path('edit_answers_ajax/<int:question_id>/', views.edit_answers_ajax, name='edit_answers_ajax'),

    # New URL for student public profile
    path('student/<int:student_id>/profile/', views.student_public_profile, name='student_public_profile'),

    # New URL for deleting a group
    path('delete_group/<int:group_id>/', views.delete_group, name='delete_group'),

    # New URL for marking notifications as read
    path('notifications/mark_read/', views.mark_notifications_read, name='mark_notifications_read'),
]

from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)