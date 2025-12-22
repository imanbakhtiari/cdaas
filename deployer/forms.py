from django import forms

from .models import Repository


class RepositoryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control').strip()

    class Meta:
        model = Repository
        fields = [
            'name',
            'url',
            'branch',
            'username',
            'password',
            'nexus_registry',
            'nexus_repository',
            'nexus_username',
            'nexus_password',
            'kubernetes_namespace',
            'kubeconfig',
        ]
        widgets = {
            'kubeconfig': forms.Textarea(attrs={'rows': 6}),
            'password': forms.PasswordInput(render_value=True),
            'nexus_password': forms.PasswordInput(render_value=True),
        }
