from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ProfileForm, RegistrationForm
from .models import UserProfile


def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    "notify_on_article_publish": form.cleaned_data["notify_on_article_publish"],
                    "notify_on_quiz_publish": form.cleaned_data["notify_on_quiz_publish"],
                },
            )
            login(request, user)
            return redirect("home")
    else:
        form = RegistrationForm()
    return render(request, "registration/register.html", {"form": form})


@login_required
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your information has been updated.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=request.user, user=request.user)
    return render(request, "registration/profile.html", {"form": form})
