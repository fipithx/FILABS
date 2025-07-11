document.addEventListener('DOMContentLoaded', function() {
    // Course filter functionality
    const roleFilter = document.querySelector('#role-filter');
    if (roleFilter) {
        roleFilter.addEventListener('change', function() {
            fetch('/learning_hub/api/set_role_filter', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: 'role=' + encodeURIComponent(this.value)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.location.reload();
                } else {
                    alert(data.message || 'Error updating role filter');
                }
            })
            .catch(error => {
                console.error('Error setting role filter:', error);
                alert('Error updating role filter');
            });
        });
    }

    // Lesson completion handler
    const lessonButtons = document.querySelectorAll('.mark-lesson-complete');
    lessonButtons.forEach(button => {
        button.addEventListener('click', function() {
            const courseId = this.dataset.courseId;
            const lessonId = this.dataset.lessonId;
            fetch('/learning_hub/api/lesson/action', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `course_id=${encodeURIComponent(courseId)}&lesson_id=${encodeURIComponent(lessonId)}&action=mark_complete`
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert(data.message);
                    if (data.coins_earned) {
                        alert(`Earned: ${data.coins_earned}`);
                    }
                    if (data.badge_earned) {
                        alert(`Badge Earned: ${data.badge_earned}`);
                    }
                    window.location.reload();
                } else {
                    alert(data.message || 'Error marking lesson complete');
                }
            })
            .catch(error => {
                console.error('Error marking lesson complete:', error);
                alert('Error marking lesson complete');
            });
        });
    });

    // Quiz submission handler
    const quizForms = document.querySelectorAll('.quiz-form');
    quizForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            formData.append('action', this.dataset.quizType === 'reality_check' ? 'submit_reality_check' : 'submit_quiz');
            fetch('/learning_hub/api/quiz/action', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    let message = `${data.message}\nScore: ${data.score}/${data.total}`;
                    if (data.passed) {
                        message += '\nPassed!';
                    }
                    if (data.coins_earned) {
                        message += `\nEarned: ${data.coins_earned}`;
                    }
                    if (data.badge_earned) {
                        message += `\nBadge Earned: ${data.badge_earned}`;
                    }
                    alert(message);
                    window.location.reload();
                } else {
                    alert(data.message || 'Error submitting quiz');
                }
            })
            .catch(error => {
                console.error('Error submitting quiz:', error);
                alert('Error submitting quiz');
            });
        });
    });
});
