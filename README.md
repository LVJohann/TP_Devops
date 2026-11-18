# TP_Devops — TaskFlow

Frontend nginx → API FastAPI → Redis + PostgreSQL, déployé sur Kubernetes (environnements `dev`, `val`, `prod`).

```
Navigateur ──> frontend (nginx :8080) ──/api/*──> api (FastAPI :8000) ──> Redis (compteur)
                                                                      └─> PostgreSQL (visites, tâches, journal)
```

## Fonctionnalités

| # | Page | Fonctionnalité |
|---|---|---|
| 1 | Visites & services | Compteur de visites (Redis) et pods qui ont répondu |
| 2 | Visites & services | Historique des visites (PostgreSQL) |
| 3 | Visites & services | État des services (API, Redis, PostgreSQL) |
| 4 | Tâches | Création d'une tâche (titre, description, priorité, échéance) |
| 5 | Tâches | Liste avec recherche, filtres (statut, priorité) et tri |
| 6 | Tâches | Changement de statut (À faire / En cours / Terminée) |
| 7 | Tâches | Modification et suppression d'une tâche |
| 8 | Tâches | Statistiques (répartition, urgentes, en retard, % terminées) |
| 9 | Tâches | Journal d'activité |

---

## Prérequis

- Docker
- `kubectl`
- [minikube](https://minikube.sigs.k8s.io/docs/start/)

## Déploiement Kubernetes (minikube)

```bash
# 1. Démarrer le cluster
minikube start
minikube addons enable ingress
minikube addons enable metrics-server        # nécessaire pour le HPA (prod)

# 2. Construire les images et les charger dans minikube
docker build -t taskflow-api:1.0 .
docker build -t taskflow-frontend:1.0 ./frontend
minikube image load taskflow-api:1.0
minikube image load taskflow-frontend:1.0

# 3. Déployer un environnement : dev, val ou prod
kubectl apply -k k8s/overlays/dev
kubectl get pods -n taskflow-dev -w          # attendre que tout soit Running / Ready
```

| Environnement | Commande | Namespace | Réplicas API | Hôte Ingress |
|---|---|---|---|---|
| dev | `kubectl apply -k k8s/overlays/dev` | `taskflow-dev` | 1 | `dev.taskflow.local` |
| val | `kubectl apply -k k8s/overlays/val` | `taskflow-val` | 1 | `val.taskflow.local` |
| prod | `kubectl apply -k k8s/overlays/prod` | `taskflow-prod` | 3 → 8 (HPA) | `taskflow.local` |

### Accéder à l'application

```bash
kubectl port-forward -n taskflow-dev svc/frontend 8080:80
```

Puis ouvrir http://localhost:8080 (page *Tâches* : http://localhost:8080/taskflow.html, API : http://localhost:8080/api/docs).

Ou via l'Ingress :
- **Linux** : `echo "$(minikube ip) dev.taskflow.local" | sudo tee -a /etc/hosts` puis http://dev.taskflow.local
- **Windows / WSL** : lancer `minikube tunnel`, ajouter `127.0.0.1 dev.taskflow.local` dans `C:\Windows\System32\drivers\etc\hosts`.

### Mettre à jour / supprimer

```bash
docker build -t taskflow-api:1.0 . && minikube image load taskflow-api:1.0
kubectl rollout restart deployment/api -n taskflow-dev

kubectl delete -k k8s/overlays/dev           # supprime l'environnement
```

## CI/CD (GitHub Actions)

À chaque push sur `main`, `dev`, `val`, `prod` (et sur les pull requests), [.github/workflows/ci-cd.yaml](.github/workflows/ci-cd.yaml) :

1. lance les tests `pytest` ;
2. valide les manifests des 3 environnements (`kubectl kustomize`) ;
3. déploie l'application sur un cluster Kubernetes éphémère (kind) — overlay `dev` pour la branche `dev`, `prod` pour `main`/`prod`, `val` sinon — et exécute des tests de fumée sur les 9 fonctionnalités ;
4. publie les images sur `ghcr.io/<owner>/taskflow-api` et `taskflow-frontend` (push uniquement).
