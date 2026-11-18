# TP_Devops — Visits

Application de comptage de visites : un **frontend web** (nginx) qui appelle une **API FastAPI**, elle-même branchée sur **Redis** (compteur) et **PostgreSQL** (historique).

```
Navigateur ──> frontend (nginx :8080) ──/api/*──> api (FastAPI :8000) ──> Redis (compteur)
                                                                      └─> PostgreSQL (historique)
```

## Les 3 fonctionnalités du frontend

| # | Fonctionnalité | Ce qu'elle fait | Endpoint API |
|---|---|---|---|
| 1 | **Compteur de visites** | Enregistre une visite (ou 10 avec `×10`), affiche le compteur et le pod qui a répondu (utile en Kubernetes pour voir la répartition de charge) | `GET /` et `GET /visits/count` |
| 2 | **Historique des visites** | Tableau des dernières visites stockées dans PostgreSQL (10 à 100 lignes) | `GET /visits?limit=20` |
| 3 | **État des services** | État de l'API, de Redis et de PostgreSQL, rafraîchi toutes les 10 s | `GET /status` |

Autres endpoints : `GET /health` (sonde Kubernetes), `GET /docs` (Swagger).
Depuis le frontend, toutes les routes de l'API sont accessibles avec le préfixe `/api` (ex. `http://localhost:8080/api/health`).

## Structure

```
app/          API FastAPI (main.py, requirements.txt)
frontend/     Frontend : public/ (HTML/CSS/JS), nginx/ (config), Dockerfile
tests/        Tests pytest
k8s/          Manifests Kubernetes (namespace, api, frontend, redis, postgres, ingress, hpa…)
Dockerfile    Image de l'API
compose.yaml  Stack complète pour Docker Compose
```

---

## 1. Prérequis

### Sous Linux (Ubuntu/Debian)

```bash
# Docker Engine + plugin compose (méthode officielle)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER     # utiliser docker sans sudo
newgrp docker                     # ou se déconnecter / reconnecter
docker compose version            # doit afficher une version
```

### Sous Windows avec WSL2

1. Installer WSL2 + Ubuntu (PowerShell admin) : `wsl --install -d Ubuntu`
2. Docker, au choix :
   - **Docker Desktop** : *Settings → Resources → WSL integration* → activer Ubuntu ;
   - **ou Docker Engine directement dans Ubuntu** : mêmes commandes que Linux ci-dessus. Si `docker` ne démarre pas, activer systemd dans `/etc/wsl.conf` :
     ```ini
     [boot]
     systemd=true
     ```
     puis `wsl --shutdown` depuis PowerShell et rouvrir Ubuntu.
3. Toutes les commandes de ce README se lancent **dans le terminal Ubuntu (WSL)**, pas dans PowerShell.
4. Conseil : cloner le dépôt dans le système de fichiers Linux (`~/...`) plutôt que dans `/mnt/c/...` (beaucoup plus rapide). Les deux fonctionnent.
5. Les ports publiés par Docker dans WSL sont accessibles depuis le navigateur Windows via `http://localhost:...`.

> Les fins de ligne sont forcées en LF par `.gitattributes`, donc pas de problème CRLF entre Windows/WSL et Linux.

---

## 2. Lancer l'application (Docker Compose) — recommandé

Identique sous Linux et WSL :

```bash
git clone <url-du-depot> TP_Devops
cd TP_Devops
docker compose up -d --build
```

Puis ouvrir :

| URL | Contenu |
|---|---|
| http://localhost:8080 | **Frontend** (les 3 fonctionnalités) |
| http://localhost:8000/docs | Documentation Swagger de l'API |
| http://localhost:8000/health | Santé de l'API |

Tester l'API en ligne de commande :

```bash
curl http://localhost:8000/            # enregistre une visite
curl http://localhost:8000/visits/count
curl "http://localhost:8000/visits?limit=5"
curl http://localhost:8000/status
curl http://localhost:8080/api/status  # même chose, en passant par le frontend
```

Commandes utiles :

```bash
docker compose ps                   # état des conteneurs
docker compose logs -f api          # logs de l'API (ou frontend, db, cache)
docker compose up -d --build        # reconstruire après une modification du code
docker compose down                 # arrêter (les données sont conservées)
docker compose down -v              # arrêter ET supprimer les données (volumes)
```

Mot de passe PostgreSQL : `app` par défaut. Pour le changer, créer un fichier `.env` à la racine (non versionné) :

```bash
echo "DB_PASSWORD=unAutreMotDePasse" > .env
```

---

## 3. Tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt pytest httpx
python -m pytest -v
```

Sous Ubuntu, si `venv` manque : `sudo apt install python3-venv`.
Les tests ne nécessitent ni Redis ni PostgreSQL.

---

## 4. Déploiement Kubernetes (minikube)

```bash
minikube start
minikube addons enable ingress
minikube addons enable metrics-server     # nécessaire pour le HPA

# Construire les images et les charger dans minikube
docker build -t visits-api:1.0 .
docker build -t visits-frontend:1.0 ./frontend
minikube image load visits-api:1.0
minikube image load visits-frontend:1.0

# Déployer
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/
kubectl get pods -n visits -w             # attendre que tout soit Running / Ready
```

Accéder au frontend — **méthode qui marche partout (Linux et WSL)** :

```bash
kubectl port-forward -n visits svc/frontend 8080:80
# puis http://localhost:8080
```

Avec l'Ingress (`http://visits.local`) :
- **Linux** : `echo "$(minikube ip) visits.local" | sudo tee -a /etc/hosts`
- **WSL** : lancer `minikube tunnel` dans un terminal, puis ajouter `127.0.0.1 visits.local` dans `C:\Windows\System32\drivers\etc\hosts` (bloc-notes en administrateur).

Avec 3 réplicas de l'API, le bouton **×10** du compteur montre plusieurs pods différents qui répondent.

Nettoyer : `kubectl delete namespace visits`

---

## 5. Dépannage

| Problème | Solution |
|---|---|
| `permission denied ... docker.sock` | `sudo usermod -aG docker $USER` puis se reconnecter (WSL : `wsl --shutdown`) |
| `Cannot connect to the Docker daemon` (WSL) | Lancer Docker Desktop, ou `sudo service docker start` / activer systemd |
| `port is already allocated` (8000 ou 8080) | Libérer le port, ou changer le port de gauche dans `compose.yaml` (ex. `"8081:8080"`) |
| Frontend affiche « API injoignable » / erreur 502 | `docker compose ps` et `docker compose logs api` ; l'API attend que PostgreSQL soit prêt |
| Redis ou PostgreSQL « Indisponible » | `docker compose logs db cache` ; repartir de zéro avec `docker compose down -v && docker compose up -d --build` |
| Modification du frontend non visible | `docker compose up -d --build frontend` puis Ctrl+F5 dans le navigateur |..
