# Docker setup

## 1-  Build the image

From the root of the github repo run

```sh
docker build -t intelligentlogistics/agenta:latest -f src/agentA_microservice/Dockerfile .


```
## 2- Login to Docker Hub 

- pass : pei2025!

```sh
docker login
```


## 3- Push image to docker hub

```sh
docker push intelligentlogistics/agenta:latest
```
## 4- Pull the image on another machine

First time (need to install docker and added the user to the docker users): 

```sh
sudo usermod -aG docker $USER
sudo reboot
```

```sh
docker pull intelligentlogistics/agenta:latest
```
## 5- Run the container

-d : run in background

```sh
docker run -d intelligentlogistics/agenta:latest
```

## 6- Check logs

-f : follow

```sh
docker logs -f serene_babbage
```
