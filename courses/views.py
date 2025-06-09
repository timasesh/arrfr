# courses/views.py
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.forms import modelformset_factory
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
import logging
from django.db.models import Count

from .forms import (
    StudentRegistrationForm, LessonCreationForm, ModuleCreationForm,
    CourseCreationForm, StudentProfileForm, QuizForm, QuestionForm,
    AnswerForm, QuizToModuleForm
)
from .models import (
    User, Lesson, Module, Course, StudentProgress, Student,
    Question, Answer, Quiz, QuizResult, ProfileEditRequest, CourseAddRequest, Notification, Group, QuizAttempt
)

logger = logging.getLogger(__name__)

# Authentication Views
def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        
        user = authenticate(request, username=username, password=password)
        if user is not None and hasattr(user, 'student'):
            login(request, user)
            return redirect('student_page')
        else:
            error_message = "Invalid username or password."
            return render(request, 'courses/login.html', {'error': error_message})
    
    return render(request, 'courses/login.html')

def logout_view(request):
    logout(request)
    return redirect('login_view')

# Admin Views
@login_required
def admin_page(request):
    from .models import ProfileEditRequest, CourseAddRequest, Notification, Group
    student_form = StudentRegistrationForm()
    lesson_form = LessonCreationForm()
    module_form = ModuleCreationForm()
    course_form = CourseCreationForm()

    if request.method == 'POST':
        if 'add_student' in request.POST:
            student_form = StudentRegistrationForm(request.POST)
            if student_form.is_valid():
                student_form.save()
                return redirect('admin_page')
        elif 'add_lesson' in request.POST:
            lesson_form = LessonCreationForm(request.POST, request.FILES)
            if lesson_form.is_valid():
                lesson_form.save()
                return redirect('admin_page')
        elif 'add_module' in request.POST:
            module_form = ModuleCreationForm(request.POST)
            if module_form.is_valid():
                module_form.save()
                return redirect('admin_page')
        elif 'add_course' in request.POST:
            course_form = CourseCreationForm(request.POST)
            if course_form.is_valid():
                course_form.save()
                return redirect('admin_page')
        elif 'delete_course' in request.POST:
            course_id = request.POST['course_id']
            Course.objects.filter(id=course_id).delete()
            return redirect('admin_page')
        elif 'approve_edit' in request.POST or 'reject_edit' in request.POST:
            req_id = request.POST.get('request_id')
            req = ProfileEditRequest.objects.get(id=req_id)
            if 'approve_edit' in request.POST:
                req.status = 'approved'
                req.admin_response = request.POST.get('admin_response', '')
                req.student.profile_edited_once = False
                req.student.save()
                Notification.objects.create(
                    student=req.student,
                    type='profile_edit',
                    message=f'Ваш запрос на редактирование профиля подтверждён. {req.admin_response or ""}'
                )
            else:
                req.status = 'rejected'
                req.admin_response = request.POST.get('admin_response', '')
                Notification.objects.create(
                    student=req.student,
                    type='profile_edit',
                    message=f'Ваш запрос на редактирование профиля отклонён. {req.admin_response or ""}'
                )
            req.save()
            return redirect('admin_page')
        elif 'approve_course_add' in request.POST or 'reject_course_add' in request.POST:
            req_id = request.POST.get('request_id')
            req = CourseAddRequest.objects.get(id=req_id)
            if 'approve_course_add' in request.POST:
                req.status = 'approved'
                req.admin_response = request.POST.get('admin_response', '')
                req.student.courses.add(req.course)
                Notification.objects.create(
                    student=req.student,
                    type='course_approved',
                    message=f'Ваш запрос на добавление курса "{req.course.title}" подтверждён. {req.admin_response or ""}'
                )
            else:
                req.status = 'rejected'
                req.admin_response = request.POST.get('admin_response', '')
                Notification.objects.create(
                    student=req.student,
                    type='course_rejected',
                    message=f'Ваш запрос на добавление курса "{req.course.title}" отклонён. {req.admin_response or ""}'
                )
            req.save()
            return redirect('admin_page')
        elif 'group_create' in request.POST:
            group_name = request.POST.get('group_name')
            student_ids = request.POST.getlist('group_students')
            if group_name and student_ids:
                group, created = Group.objects.get_or_create(name=group_name)
                new_students = Student.objects.filter(id__in=student_ids)
                old_students = set(group.students.all())
                group.students.set(new_students)
                group.save()
                # Уведомления для новых участников
                for student in new_students:
                    if student not in old_students:
                        Notification.objects.create(
                            student=student,
                            type='profile_edit',
                            message=f'Вы присоединились к группе "{group.name}".'
                        )
                        # Уведомления для остальных участников
                        for other in new_students:
                            if other != student:
                                Notification.objects.create(
                                    student=other,
                                    type='profile_edit',
                                    message=f'К вам в группу "{group.name}" присоединился {student.user.username}.'
                                )
                messages.success(request, f'Группа "{group_name}" создана!')
            return redirect('admin_page')

    students = Student.objects.all()
    lessons = Lesson.objects.all()
    modules = Module.objects.all()
    courses = Course.objects.all()
    quizzes = Quiz.objects.all()
    available_lessons = Lesson.objects.all()  # Все доступные уроки
    edit_requests = ProfileEditRequest.objects.filter(status='pending').select_related('student__user')
    course_add_requests = CourseAddRequest.objects.filter(status='pending').select_related('student__user', 'course')
    groups = Group.objects.all().prefetch_related('students')

    # Формируем словарь прогресса для быстрого доступа в шаблоне (по факту завершённых уроков)
    progress_dict = {}
    for student in students:
        for course in student.courses.all():
            # Создаём объект прогресса, если его нет
            sp, created = StudentProgress.objects.get_or_create(user=student.user, course=course)
            # Получаем все уроки курса
            all_lessons = set()
            for module in course.modules.all():
                all_lessons.update(module.lessons.values_list('id', flat=True))
            all_lessons_count = len(all_lessons)
            completed_lessons = set(sp.completed_lessons.values_list('id', flat=True))
            if all_lessons_count > 0:
                percent = int((len(completed_lessons) / all_lessons_count) * 100)
            else:
                percent = 0
            sp.progress = percent
            sp.save()
            key = f'{student.user.id}_{course.id}'
            progress_dict[key] = percent

    context = {
        'student_form': student_form,
        'lesson_form': lesson_form,
        'module_form': module_form,
        'course_form': course_form,
        'students': students,
        'lessons': lessons,
        'modules': modules,
        'courses': courses,
        'quizzes': quizzes,
        'available_lessons': available_lessons,  # Добавляем в контекст
        'progress_dict': progress_dict,          # Новый словарь для шаблона
        'edit_requests': edit_requests,
        'course_add_requests': course_add_requests,
        'groups': groups,
    }
    return render(request, 'courses/admin_page_test.html', context)

# Student Views
@login_required
def student_page(request):
    student = get_object_or_404(Student, user=request.user)
    courses = student.courses.all()
    from .models import QuizResult, Quiz, CourseAddRequest, Course
    quiz_results = QuizResult.objects.filter(user=request.user)
    for result in quiz_results:
        quiz = getattr(result, 'quiz', None)
        if quiz and hasattr(quiz, 'stars') and quiz.stars > 0 and not result.stars_given:
            percent = int((result.score / result.total_questions) * 100) if hasattr(result, 'total_questions') and result.total_questions else 0
            if percent == 100:
                student.stars += quiz.stars
                result.stars_given = True
                result.save()
                student.save()
    
    # Convert progress_data to a dictionary with course IDs as keys
    progress_data = {}
    for course in courses:
        progress = StudentProgress.objects.filter(user=request.user, course=course).first()
        progress_data[course.id] = progress.progress if progress else 0

    show_course_notification = False
    all_courses = Course.objects.all()
    add_course_requests = CourseAddRequest.objects.filter(student=student).order_by('-created_at')
    notifications = Notification.objects.filter(student=student).order_by('-created_at')[:20]
    groups = student.groups.all().prefetch_related('students__user')
    unread_count = Notification.objects.filter(student=student, is_read=False).count()
    
    if request.method == 'POST':
        if 'course_code' in request.POST:
            course_code = request.POST.get('course_code')
            try:
                course = Course.objects.get(course_code=course_code)
                student.courses.add(course)
                show_course_notification = True
                Notification.objects.create(
                    student=student,
                    type='course_approved',
                    message=f'Вы были добавлены на курс "{course.title}" через код.'
                )
                return render(request, 'courses/student_page.html', {
                    'courses': student.courses.all(),
                    'progress_data': progress_data,
                    'student': student,
                    'show_course_notification': show_course_notification,
                    'all_courses': all_courses,
                    'add_course_requests': add_course_requests,
                    'notifications': notifications,
                    'groups': groups,
                    'unread_count': unread_count,
                })
            except Course.DoesNotExist:
                error_message = "Курс с данным кодом не найден."
                return render(request, 'courses/student_page.html', {
                    'courses': courses,
                    'progress_data': progress_data,
                    'error_message': error_message,
                    'student': student,
                    'all_courses': all_courses,
                    'add_course_requests': add_course_requests,
                    'notifications': notifications,
                    'groups': groups,
                    'unread_count': unread_count,
                })
        elif 'add_course_request' in request.POST:
            course_id = request.POST.get('course_id')
            comment = request.POST.get('comment')
            course = get_object_or_404(Course, id=course_id)
            CourseAddRequest.objects.create(student=student, course=course, comment=comment)
            Notification.objects.create(
                student=student,
                type='course_approved',
                message=f'Ваш запрос на добавление курса "{course.title}" отправлен администратору.'
            )
            messages.success(request, 'Запрос на добавление курса отправлен!')
            return redirect('student_page')
    
    return render(request, 'courses/student_page.html', {
        'courses': courses,
        'progress_data': progress_data,
        'student': student,
        'show_course_notification': show_course_notification,
        'all_courses': all_courses,
        'add_course_requests': add_course_requests,
        'notifications': notifications,
        'groups': groups,
        'unread_count': unread_count,
    })

@login_required
def student_profile(request):
    student = get_object_or_404(Student, user=request.user)
    from .models import ProfileEditRequest

    # Проверяем наличие активного запроса
    active_request = ProfileEditRequest.objects.filter(student=student, status='pending').first()
    last_request = ProfileEditRequest.objects.filter(student=student).order_by('-created_at').first()
    admin_response = None
    admin_status = None
    if last_request and last_request.status in ['approved', 'rejected']:
        admin_response = last_request.admin_response
        admin_status = last_request.status

    if request.method == 'POST':
        if 'request_edit' in request.POST:
            # Создать заявку на редактирование
            if not active_request:
                ProfileEditRequest.objects.create(student=student)
                Notification.objects.create(
                    student=student,
                    type='profile_edit',
                    message='Ваш запрос на редактирование профиля отправлен администратору.'
                )
                messages.success(request, 'Запрос на редактирование отправлен администратору.')
            return redirect('student_profile')
        else:
            form = StudentProfileForm(request.POST, request.FILES, instance=student)
            if form.is_valid():
                form.save()
                student.profile_edited_once = True
                student.save()
                return redirect('student_profile')
    else:
        form = StudentProfileForm(instance=student)

    return render(request, 'courses/student_profile.html', {
        'form': form,
        'student': student,
        'active_request': active_request,
        'admin_response': admin_response,
        'admin_status': admin_status,
    })

# Student Management Views
@login_required
def student_details(request, user_id):
    student = get_object_or_404(Student, user_id=user_id)
    
    # Подготовка данных о прогрессе
    progress_data = []
    for course in student.courses.all():
        progress = StudentProgress.objects.filter(user=student.user, course=course).first()
        progress_data.append({
            'course': course.title,
            'progress': progress.progress if progress else 0,
        })

    return render(request, 'courses/student_details.html', {
        'student': student,
        'progress_data': progress_data,
    })

# Course Management Views
@login_required
def course_detail(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    quiz_results = {}
    for module in course.modules.all():
        for quiz in module.quizzes.all():
            result = QuizAttempt.objects.filter(student__user=request.user, quiz=quiz).order_by('-attempt_number').first()
            if result:
                quiz_results[quiz.id] = {
                    'score': result.score,
                    'passed': result.passed,
                    'percent': result.score
                }
    student_progress = StudentProgress.objects.filter(user=request.user, course=course).first()
    completed_lessons = set()
    if student_progress:
        completed_lessons = set(student_progress.completed_lessons.values_list('id', flat=True))
    # Прогресс по каждому модулю
    module_progress = {}
    for module in course.modules.all():
        lessons = list(module.lessons.all())
        if lessons:
            completed = sum(1 for lesson in lessons if lesson.id in completed_lessons)
            percent = int((completed / len(lessons)) * 100)
        else:
            percent = 0
        module_progress[module.id] = percent
    # Для блокировки уроков по модулю
    next_lesson_id_by_module = {}
    for module in course.modules.all():
        for lesson in module.lessons.all():
            if lesson.id not in completed_lessons:
                next_lesson_id_by_module[module.id] = lesson.id
                break
    return render(request, 'courses/course_detail.html', {
        'course': course,
        'quiz_results': quiz_results,
        'student_progress': student_progress,
        'completed_lessons': completed_lessons,
        'module_progress': module_progress,
        'next_lesson_id_by_module': next_lesson_id_by_module
    })

@login_required
def create_course(request):
    if request.method == 'POST':
        course_form = CourseCreationForm(request.POST, request.FILES)
        if course_form.is_valid():
            course_form.save()
            return redirect('admin_page')
    else:
        course_form = CourseCreationForm()

    courses = Course.objects.all()
    return render(request, 'courses/create_course.html', {
        'course_form': course_form,
        'courses': courses,
    })

@login_required
def delete_course(request, course_id):
    if request.method == 'POST':
        course = get_object_or_404(Course, id=course_id)
        course.delete()
        return redirect('admin_page')
    return JsonResponse({'error': 'Метод не разрешен'}, status=405)

# Module Management Views
@login_required
def create_module(request):
    if request.method == 'POST':
        module_form = ModuleCreationForm(request.POST)
        if module_form.is_valid():
            module_form.save()
            return redirect('admin_page')
    else:
        module_form = ModuleCreationForm()

    return render(request, 'courses/create_module.html', {
        'module_form': module_form,
    })

@login_required
def module_details(request, module_id):
    module = Module.objects.get(id=module_id)
    lessons = Lesson.objects.filter(module=module)
    return render(request, 'courses/module_details.html', {
        'module': module,
        'lessons': lessons,
    })

@login_required
def delete_module(request, module_id):
    module = get_object_or_404(Module, id=module_id)
    if request.method == 'POST':
        module.delete()
        return redirect('admin_page')
    return render(request, 'courses/delete_module.html', {'module': module})

def detach_module(request, course_id, module_id):
    course = get_object_or_404(Course, id=course_id)
    module = get_object_or_404(Module, id=module_id)
    course.modules.remove(module)
    return redirect('admin_page')

@login_required
def add_module_to_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    modules = Module.objects.all()

    if request.method == 'POST':
        selected_module_id = request.POST.get('module_id')
        if selected_module_id:
            module = get_object_or_404(Module, id=selected_module_id)
            course.modules.add(module)
            messages.success(request, 'Модуль успешно добавлен к курсу.')
            return redirect('admin_page')

    return render(request, 'courses/add_module_to_course.html', {
        'course': course,
        'modules': modules,
    })

# Lesson Management Views
@login_required
def create_lesson(request, module_id=None):
    if request.method == 'POST':
        lesson_form = LessonCreationForm(request.POST, request.FILES)
        if lesson_form.is_valid():
            lesson = lesson_form.save()
            if module_id:
                module = Module.objects.get(id=module_id)
                module.lessons.add(lesson)
                module.save()
            return redirect('admin_page')
    else:
        lesson_form = LessonCreationForm()

    return render(request, 'courses/create_lesson.html', {
        'lesson_form': lesson_form,
        'module_id': module_id,
    })

@login_required
def view_lesson(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if request.method == 'POST' and 'update_title' in request.POST:
        new_title = request.POST.get('title', '').strip()
        if new_title:
            lesson.title = new_title
            lesson.save()
    return render(request, 'courses/view_lesson.html', {'lesson': lesson})

@login_required
def delete_lesson(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if request.method == 'POST':
        lesson.delete()
        return redirect('admin_page')
    return render(request, 'courses/delete_lesson.html', {'lesson': lesson})

@login_required
def replace_video(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if request.method == 'POST' and request.FILES.get('new_video'):
        lesson.video = request.FILES['new_video']
        lesson.save()
        return redirect('view_lesson', lesson_id=lesson.id)
    return HttpResponse("Ошибка при замене видео.", status=400)

@login_required
def replace_pdf(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if request.method == 'POST' and request.FILES.get('new_pdf'):
        lesson.pdf = request.FILES['new_pdf']
        lesson.save()
        return redirect('view_lesson', lesson_id=lesson.id)
    return HttpResponse("Ошибка при замене PDF.", status=400)

@login_required
def edit_lesson(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if request.method == 'POST':
        form = LessonCreationForm(request.POST, request.FILES, instance=lesson)
        if form.is_valid():
            form.save()
            return redirect('view_lesson', lesson_id=lesson.id)
    else:
        form = LessonCreationForm(instance=lesson)
    return render(request, 'courses/edit_lesson.html', {'form': form, 'lesson': lesson})

# Quiz Management Views
@login_required
def create_quiz(request):
    if request.method == 'POST':
        quiz_form = QuizForm(request.POST)
        if quiz_form.is_valid():
            quiz = quiz_form.save()
            return redirect('add_question', quiz_id=quiz.id)
    else:
        quiz_form = QuizForm()

    return render(request, 'courses/create_quiz.html', {
        'quiz_form': quiz_form,
    })

@login_required
def add_question(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    AnswerFormSet = modelformset_factory(Answer, form=AnswerForm, extra=4)

    if request.method == 'POST':
        question_form = QuestionForm(request.POST)
        formset = AnswerFormSet(request.POST)

        if question_form.is_valid() and formset.is_valid():
            question = question_form.save(commit=False)
            question.quiz = quiz
            question.save()

            answers = formset.save(commit=False)
            for answer in answers:
                answer.question = question
                answer.save()

            return redirect('add_question', quiz_id=quiz_id)
    else:
        question_form = QuestionForm()
        formset = AnswerFormSet(queryset=Answer.objects.none())

    return render(request, 'courses/add_question.html', {
        'question_form': question_form,
        'formset': formset,
        'quiz': quiz,
    })

@login_required
def quiz_list(request):
    quizzes = Question.objects.all()
    return render(request, 'courses/quiz_list.html', {'quizzes': quizzes})

@login_required
def start_quiz(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    student = get_object_or_404(Student, user=request.user)
    module = quiz.module_set.first()
    if not module:
        messages.error(request, 'Квиз не привязан ни к одному модулю. Обратитесь к администратору.')
        # Попробуем найти курс через quiz.course_set.first(), если есть связь
        course = None
        if hasattr(quiz, 'course_set') and quiz.course_set.exists():
            course = quiz.course_set.first()
            return redirect('course_detail', course_id=course.id)
        return redirect('student_page')
    course = module.course_set.first()
    if not course:
        messages.error(request, 'Модуль не привязан ни к одному курсу.')
        return redirect('student_page')
    if course not in student.courses.all():
        messages.error(request, 'Вы не записаны на этот курс.')
        return redirect('student_page')
    student_progress = StudentProgress.objects.filter(user=request.user, course=course).first()
    if not student_progress:
        messages.error(request, 'У вас нет прогресса по этому курсу.')
        return redirect('student_page')
    module_lessons = module.lessons.all()
    completed_lessons = student_progress.completed_lessons.all()
    uncompleted_lessons = [lesson for lesson in module_lessons if lesson not in completed_lessons]
    if uncompleted_lessons:
        messages.error(request, f'Для доступа к квизу необходимо пройти все уроки модуля "{module.title}". Осталось пройти {len(uncompleted_lessons)} уроков.')
        return redirect('course_detail', course_id=course.id)
    # Проверяем, сдан ли квиз на 70+
    from .models import QuizAttempt
    last_attempt = QuizAttempt.objects.filter(student=student, quiz=quiz).order_by('-attempt_number').first()
    if last_attempt and last_attempt.passed:
        return redirect('quiz_result', quiz_id=quiz.id)
    if request.method == 'POST':
        correct = 0
        total = quiz.questions.count()
        for question in quiz.questions.all():
            user_answer = request.POST.get(f'question_{question.id}')
            correct_answer = question.answers.filter(is_correct=True).first()
            if user_answer and correct_answer and user_answer == correct_answer.text:
                correct += 1
        percent = int((correct / total) * 100) if total else 0
        passed = percent >= 70
        # Определяем номер попытки
        attempt_number = 1
        if last_attempt:
            attempt_number = last_attempt.attempt_number + 1
        # Штраф за неудачу
        stars_penalty = 0
        if not passed:
            stars_penalty = attempt_number * 5
            student.stars = max(0, student.stars - stars_penalty)
            student.save()
        QuizAttempt.objects.create(
            student=student,
            quiz=quiz,
            score=percent,
            passed=passed,
            attempt_number=attempt_number,
            stars_penalty=stars_penalty
        )
        if passed:
            messages.success(request, f'Квиз сдан! Ваш результат: {percent}%.')
        else:
            messages.error(request, f'Квиз не сдан (результат: {percent}%). Штраф: -{stars_penalty} звёзд. Попробуйте ещё раз.')
        return redirect('quiz_result', quiz_id=quiz.id)
    return render(request, 'courses/quiz.html', {
        'quiz': quiz,
        'questions': quiz.questions.all()
    })

@login_required
def quiz_result(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    student = get_object_or_404(Student, user=request.user)
    module = quiz.module_set.first()
    course = None
    if module:
        course = module.course_set.first()
    from .models import QuizAttempt
    last_attempt = QuizAttempt.objects.filter(student=student, quiz=quiz).order_by('-attempt_number').first()
    percent = int(last_attempt.score) if last_attempt else 0
    show_stars_notification = False
    stars_awarded = 0
    if last_attempt and last_attempt.passed and last_attempt.attempt_number == 1:
        # Можно начислить звёзды только за первую успешную сдачу
        if quiz.stars > 0:
            student.stars += quiz.stars
            student.save()
            stars_awarded = quiz.stars
            show_stars_notification = True
            Notification.objects.create(
                student=student,
                type='stars_awarded',
                message=f'Поздравляем! Вы получили {quiz.stars} звёзд за квиз "{quiz.title}".'
            )
    # Обновляем прогресс
    if course:
        progress = student.calculate_progress(course)
        sp = StudentProgress.objects.filter(user=student.user, course=course).first()
        if sp:
            sp.progress = progress
            sp.save()
    return render(request, 'courses/quiz_result.html', {
        'quiz': quiz,
        'result': last_attempt,
        'course': course,
        'percent': percent,
        'show_stars_notification': show_stars_notification,
        'stars_awarded': stars_awarded,
    })

@login_required
def delete_quiz(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    if request.method == 'POST':
        quiz.delete()
        return redirect('admin_page')
    return JsonResponse({'error': 'Метод не разрешен'}, status=405)

@login_required
def bind_quiz_to_module(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)

    if request.method == 'POST':
        form = QuizToModuleForm(request.POST)
        if form.is_valid():
            course = form.cleaned_data['course']
            module = form.cleaned_data['module']
            module.quizzes.add(quiz)
            messages.success(request, 'Квиз успешно привязан к модулю.')
            return redirect('admin_page')
    else:
        form = QuizToModuleForm(initial={'quiz': quiz})

    return render(request, 'courses/choose.html', {'form': form, 'quiz': quiz})

@login_required
def edit_quiz(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk)
    
    if request.method == 'POST':
        form = QuizForm(request.POST, instance=quiz)
        
        if form.is_valid():
            # Сохраняем основную информацию о квизе
            quiz = form.save()
            
            # Получаем все существующие вопросы
            existing_questions = quiz.questions.all()
            
            # Обрабатываем каждый вопрос
            question_ids = request.POST.getlist('question_id[]')
            question_texts = request.POST.getlist('question_text[]')
            
            # Создаем множество ID вопросов, которые нужно сохранить
            questions_to_keep = set()
            
            # Обновляем или создаем вопросы
            for i, (question_id, question_text) in enumerate(zip(question_ids, question_texts)):
                if question_text.strip():  # Проверяем, что текст не пустой
                    if question_id:  # Обновляем существующий вопрос
                        question = Question.objects.get(id=question_id)
                        question.text = question_text
                        question.save()
                    else:  # Создаем новый вопрос
                        question = Question.objects.create(quiz=quiz, text=question_text)
                    
                    questions_to_keep.add(question.id)
                    
                    # Обрабатываем ответы для вопроса
                    answer_texts = request.POST.getlist(f'answer_text_{question.id}')
                    correct_answer = request.POST.get(f'answer_{question.id}')
                    
                    # Удаляем старые ответы
                    question.answers.all().delete()
                    
                    # Создаем новые ответы
                    for j, text in enumerate(answer_texts):
                        if text.strip():  # Проверяем, что текст не пустой
                            Answer.objects.create(
                                question=question,
                                text=text,
                                is_correct=(str(j) == correct_answer)
                            )
            
            # Удаляем вопросы, которых нет в списке для сохранения
            for question in existing_questions:
                if question.id not in questions_to_keep:
                    question.delete()
            
            messages.success(request, 'Квиз успешно обновлен!')
            return redirect('admin_page')
    else:
        form = QuizForm(instance=quiz)
    
    # Подготавливаем данные для шаблона
    questions_data = []
    for question in quiz.questions.all():
        questions_data.append({
            'id': question.id,
            'text': question.text,
            'answers': question.answers.all(),
            'correct_answer_index': next((i for i, a in enumerate(question.answers.all()) if a.is_correct), 0)
        })
    
    return render(request, 'courses/edit_quiz.html', {
        'form': form,
        'quiz': quiz,
        'questions_data': questions_data
    })

@login_required
def success_view(request):
    return render(request, 'courses/success.html')

# Progress Tracking Views
@csrf_exempt
def update_progress(request):
    if request.method == 'POST':
        lesson_id = request.POST.get('lesson_id')
        course_id = request.POST.get('course_id')
        user = request.user

        try:
            course = Course.objects.get(id=course_id)
            lesson = Lesson.objects.get(id=lesson_id)
            student_progress, created = StudentProgress.objects.get_or_create(user=user, course=course)

            if lesson not in student_progress.completed_lessons.all():
                student_progress.completed_lessons.add(lesson)

            modules = course.modules.all()
            total_lessons = Lesson.objects.filter(module__in=modules).distinct().count()
            completed_lessons = student_progress.completed_lessons.count()

            if total_lessons > 0:
                progress = int((completed_lessons / total_lessons) * 100)
            else:
                progress = 0

            student_progress.progress = max(0, min(progress, 100))
            student_progress.save()

            return JsonResponse({'success': True, 'progress': student_progress.progress})
        except (Course.DoesNotExist, Lesson.DoesNotExist) as e:
            return JsonResponse({'success': False, 'error': 'Курс или урок не найден.'})
    return JsonResponse({'success': False, 'error': 'Некорректный запрос.'})

# Helper Functions
def calculate_score(post_data, quiz):
    score = 0
    for question in quiz.questions.all():
        user_answer = post_data.get(f'question_{question.id}')
        # Найти правильный ответ
        correct_answer = question.answers.filter(is_correct=True).first()
        if user_answer and correct_answer and user_answer == correct_answer.text:
            score += 1
    return score

# User Management Views
@login_required
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        user.delete()
        return redirect('admin_page')
    return render(request, 'courses/delete_student.html', {'student': user})

@login_required
def detach_course(request, user_id, course_id):
    if request.method == 'POST':
        student = get_object_or_404(Student, user_id=user_id)
        course = get_object_or_404(Course, id=course_id)
        
        # Открепляем курс от студента
        student.courses.remove(course)
        
        # Удаляем прогресс по этому курсу
        StudentProgress.objects.filter(user=student.user, course=course).delete()
        
        messages.success(request, f'Курс "{course.title}" успешно откреплен от студента {student.user.username}')
        return redirect('admin_page')
    
    return redirect('admin_page')

@login_required
def quiz_detail(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    questions = quiz.questions.all()
    # Проверяем, проходил ли пользователь этот квиз
    result = QuizResult.objects.filter(user=request.user, quiz=quiz).first()
    percent = None
    date_taken = None
    if result and result.total_questions:
        percent = int((result.score / result.total_questions) * 100)
        date_taken = result.date_taken
    context = {
        'quiz': quiz,
        'questions': questions,
        'result': result,
        'percent': percent,
        'date_taken': date_taken
    }
    return render(request, 'courses/quiz_detail.html', context)

@login_required
def detach_lesson_from_module(request, lesson_id, module_id):
    module = get_object_or_404(Module, id=module_id)
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if request.method == 'POST':
        module.lessons.remove(lesson)
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
def add_lesson_to_module(request, module_id):
    if request.method == 'POST':
        module = get_object_or_404(Module, id=module_id)
        lesson_id = request.POST.get('lesson_id')
        lesson = get_object_or_404(Lesson, id=lesson_id)
        
        # Проверяем, не добавлен ли уже этот урок в модуль
        if lesson in module.lessons.all():
            return JsonResponse({
                'success': False,
                'error': 'Этот урок уже добавлен в модуль'
            })
        
        module.lessons.add(lesson)
        return JsonResponse({
            'success': True,
            'lesson': {
                'id': lesson.id,
                'title': lesson.title
            }
        })
    return JsonResponse({'success': False, 'error': 'Неверный метод запроса'})

@login_required
def edit_answers_ajax(request, question_id):
    question = get_object_or_404(Question, id=question_id)
    AnswerFormSet = modelformset_factory(Answer, fields=('text', 'is_correct'), extra=0, can_delete=True)
    if request.method == 'POST':
        formset = AnswerFormSet(request.POST, queryset=question.answers.all())
        if formset.is_valid():
            formset.save()
            return HttpResponse('Сохранено!')
    else:
        formset = AnswerFormSet(queryset=question.answers.all())
    return render(request, 'courses/answer_formset_block.html', {'formset': formset, 'question': question})

@login_required
def remove_course_from_student(request, course_id):
    if request.method == 'POST':
        student = get_object_or_404(Student, user=request.user)
        course = get_object_or_404(Course, id=course_id)
        student.courses.remove(course)
        # Also remove any progress data for this course
        StudentProgress.objects.filter(user=request.user, course=course).delete()
        return redirect('student_page')
    return redirect('student_page')

@login_required
def student_public_profile(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    user = student.user
    # Курсы и прогресс
    courses = student.courses.all()
    course_progress = {}
    for course in courses:
        progress_obj = StudentProgress.objects.filter(user=user, course=course).first()
        course_progress[course.id] = progress_obj.progress if progress_obj else 0
    # Группы и рейтинг в группе
    groups = student.groups.all()
    group_ratings = []
    for group in groups:
        group_students = list(group.students.all())
        # Сортировка по звёздам (убывание)
        sorted_students = sorted(group_students, key=lambda s: s.stars, reverse=True)
        place = sorted_students.index(student) + 1 if student in sorted_students else '-'
        group_ratings.append({
            'group': group,
            'place': place,
            'total': len(sorted_students)
        })
    # Пройденные квизы
    quiz_results = QuizResult.objects.filter(user=user).select_related('quiz').order_by('-date_taken')
    quizzes = [
        {
            'quiz': qr.quiz,
            'score': qr.score,
            'total_questions': qr.total_questions,
            'date_taken': qr.date_taken
        }
        for qr in quiz_results
    ]
    # Количество звёзд
    stars = student.stars
    # Передача данных в шаблон
    return render(request, 'courses/student_public_profile.html', {
        'student': student,
        'stars': stars,
        'groups': groups,
        'group_ratings': group_ratings,
        'courses': courses,
        'quizzes': quizzes,
    })

@login_required
def delete_group(request, group_id):
    from .models import Group
    group = get_object_or_404(Group, id=group_id)
    if request.method == 'POST':
        group.delete()
        return redirect('admin_page')
    return JsonResponse({'error': 'Метод не разрешен'}, status=405)

@login_required
@require_POST
def mark_notifications_read(request):
    Notification.objects.filter(student__user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'success': True})

@login_required
def student_dashboard(request):
    student = get_object_or_404(Student, user=request.user)
    enrollments = []
    for course in student.courses.all():
        progress = student.calculate_progress(course)
        # Обновим прогресс в StudentProgress
        sp = StudentProgress.objects.filter(user=student.user, course=course).first()
        if sp:
            sp.progress = progress
            sp.save()
        enrollments.append({
            'course': course,
            'progress': progress
        })
    context = {
        'student': student,
        'enrollments': enrollments,
    }
    return render(request, 'student_dashboard.html', context)

# New AJAX view to get lesson content
def get_lesson_content(request, lesson_id):
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        data = {
            'title': lesson.title,
            'video_url': lesson.video.url if lesson.video else None,
            'pdf_url': lesson.pdf.url if lesson.pdf else None,
        }
        return JsonResponse(data)
    except Lesson.DoesNotExist:
        return JsonResponse({'error': 'Lesson not found'}, status=404)
