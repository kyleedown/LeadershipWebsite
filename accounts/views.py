from django.contrib.auth import login
from django.shortcuts import redirect, render

from .forms import RegistrationForm
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
