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

À chaque push sur `main`, `dev`, `val`, `prod` (et sur les pull requests), [.github/workflows/ci-cd.yaml](.github/workflows/ci-cd.yaml) enchaîne 4 jobs :

```
test ──┐
       ├──> deploy-kind ──> publish
manifests ┘
```

| Job | Rôle |
|---|---|
| `test` | Tests `pytest` de l'API (sans Redis ni PostgreSQL) |
| `manifests` | `kubectl kustomize` des overlays `dev`, `val` et `prod` |
| `deploy-kind` | Build des images, cluster Kubernetes éphémère (kind), `kubectl apply -k`, attente des rollouts, tests de fumée des 9 fonctionnalités via le frontend nginx. Overlay choisi selon la branche : `dev` → dev, `main`/`prod` → prod, sinon val. En cas d'échec, l'état du cluster et les logs des pods sont publiés en annotations sur la page du run. |
| `publish` | Push des images `ghcr.io/lvjohann/taskflow-api` et `taskflow-frontend` (tags `<sha>` et `<branche>`), uniquement sur push |

### Bilan CI/CD (branche `val`, 18/11/2026)

| Run | Commit | Résultat | Détail |
|---|---|---|---|
| [#1](https://github.com/LVJohann/TP_Devops/actions/runs/44291026705) | `c2a39b9` | ❌ échec | `test` et `manifests` OK ; `deploy-kind` en échec, cause non visible (logs détaillés réservés aux membres du dépôt) |
| [#2](https://github.com/LVJohann/TP_Devops/actions/runs/44294093674) | `fba3df6` | ❌ échec | Ajout du diagnostic en annotations : PostgreSQL, Redis et frontend `Running`, mais l'API en `CrashLoopBackOff` → `ValueError: invalid literal for int(): 'tcp://10.96.188.116:6379'` |
| [#3](https://github.com/LVJohann/TP_Devops/actions/runs/44295084650) | `18061c0` | ✅ succès | Correctif appliqué, les 4 jobs sont verts |

**Cause de l'échec :** Kubernetes injecte automatiquement dans chaque pod des variables pour les Services du namespace. Pour le Service `redis`, il crée `REDIS_PORT=tcp://<ip>:6379`, ce qui écrasait la variable de port lue par l'API. Le bug était invisible avec Docker Compose et n'est apparu qu'au déploiement Kubernetes.
**Correctif :** variable renommée en `REDIS_TCP_PORT`, `enableServiceLinks: false` sur le Deployment de l'API, et test de non-régression `test_starts_with_kubernetes_service_links`.

**Run #3 (vert) :**

| Job | Durée | Vérifié |
|---|---|---|
| `test` | 34 s | 10 tests `pytest` passent |
| `manifests` | 8 s | Les 3 overlays (dev, val, prod) se génèrent |
| `deploy-kind` | 92 s | Namespace `taskflow-val` : PostgreSQL, Redis, API et frontend `Ready` ; via `/api/*` : page TaskFlow servie, `/status` = `ok` (Redis + PostgreSQL joignables), visite enregistrée, historique, création d'une tâche en base, changement de statut, recherche filtrée, statistiques, suppression (204), journal d'activité |
| `publish` | 36 s | Images publiées sur GHCR |

**Vérifié aussi en local (Docker Compose) :** des tâches ajoutées depuis le frontend sont bien relues directement dans PostgreSQL avec `psql` (tables `tasks` et `activity`), et elles sont toujours là après un redémarrage de PostgreSQL et de l'API (volume persistant).
