from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import RepositoryForm
from .models import Repository


def index(request):
    repos = Repository.objects.all().order_by('-created_at')
    if request.method == 'POST':
        form = RepositoryForm(request.POST)
        if form.is_valid():
            repo = form.save()
            messages.success(request, f"Repository '{repo.name}' added.")
            return redirect(reverse('deployer:index'))
        messages.error(request, 'Please fix the errors below.')
    else:
        form = RepositoryForm()
    return render(request, 'deployer/index.html', {'repos': repos, 'form': form})
