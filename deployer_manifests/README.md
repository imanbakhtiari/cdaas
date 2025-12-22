This directory is populated at runtime by the `watch_repos` management command.

Every repository gets a `<slug>.yaml` manifest that mirrors the data entered in
the Django admin (repository metadata, Nexus credentials, and kubeconfig).
These manifests can be consumed by other automation or inspected manually.***
