pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '15'))
    timeout(time: 30, unit: 'MINUTES')
  }

  environment {
    IMAGE_REPO  = 'ghcr.io/davidgarciabarboza-15/medisur-api'
    K8S_HOST    = 'IP_PRIVADA_DE_VM_K8S'
    APP_VERSION = '1.0.1.4'
    NAMESPACE   = 'medisur'
  }

  stages {

    // Etapa 1-2: Jenkins ya clonó el commit exacto. Aquí se calcula la etiqueta.
    stage('Preparación') {
      steps {
        script {
          env.GIT_SHA    = sh(script: 'git rev-parse --short=7 HEAD', returnStdout: true).trim()
          env.IMAGE_TAG  = "${env.APP_VERSION}-${env.GIT_SHA}"       // ej. 1.0.0-a3f9c1b  (NUNCA latest)
          env.BUILD_DATE = sh(script: 'date -u +%Y-%m-%dT%H:%M:%SZ', returnStdout: true).trim()
          currentBuild.displayName = "#${env.BUILD_NUMBER} ${env.IMAGE_TAG}"
        }
        echo "Commit ${env.GIT_SHA} -> imagen ${env.IMAGE_REPO}:${env.IMAGE_TAG}"
      }
    }

    // Etapa 3: dependencias con versiones fijadas (requirements*.txt), dentro de un contenedor.
    stage('Dependencias') {
      steps {
        sh '''
          docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
            -v "$PWD":/src -w /src python:3.12-slim \
            pip install --no-cache-dir --target .deps -r requirements-dev.txt
        '''
      }
    }

    // Etapa 4: pruebas unitarias + reporte de cobertura. Si una prueba falla, se detiene.
    stage('Pruebas unitarias') {
      steps {
        sh '''
          docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONPATH=/src/.deps \
            -v "$PWD":/src -w /src python:3.12-slim \
            python -m pytest --cov --cov-report=xml:coverage.xml --cov-report=term --junitxml=report.xml
        '''
      }
      post {
        always { junit allowEmptyResults: true, testResults: 'report.xml' }
      }
    }

    // Etapa 5: envía código y cobertura a SonarQube (escáner en contenedor).
    stage('Análisis SonarQube') {
      steps {
        withSonarQubeEnv('sonarqube') {
          sh '''
            export SONAR_TOKEN="$SONAR_AUTH_TOKEN"
            docker run --rm --network host --user "$(id -u):$(id -g)" \
              -e SONAR_HOST_URL -e SONAR_TOKEN -e SONAR_USER_HOME=/tmp/.sonar \
              -v "$PWD":/usr/src \
              sonarsource/sonar-scanner-cli \
              -Dsonar.projectVersion="$IMAGE_TAG" -Dsonar.scm.disabled=true
          '''
        }
      }
    }

    // Etapa 6: PUERTA DE CALIDAD. abortPipeline: true => si Sonar reprueba, el pipeline se detiene.
    stage('Quality Gate') {
      steps {
        timeout(time: 5, unit: 'MINUTES') {
          waitForQualityGate abortPipeline: true
        }
      }
    }

    // Etapa 7: construcción de la imagen con el SHA inyectado (lo que muestra /version).
    stage('Construcción de imagen') {
      steps {
        sh '''
          docker build \
            --build-arg APP_VERSION="$APP_VERSION" \
            --build-arg GIT_SHA="$GIT_SHA" \
            --build-arg BUILD_DATE="$BUILD_DATE" \
            -t "$IMAGE_REPO:$IMAGE_TAG" .
        '''
      }
    }

    // Etapa 8: publicar en GHCR. Solo desde main (las ramas validan pero no publican).
    stage('Publicación') {
      when { branch 'main' }
      steps {
        withCredentials([usernamePassword(credentialsId: 'github-pat',
                                          usernameVariable: 'GH_USER',
                                          passwordVariable: 'GH_TOKEN')]) {
          sh '''
            echo "$GH_TOKEN" | docker login ghcr.io -u "$GH_USER" --password-stdin
            docker push "$IMAGE_REPO:$IMAGE_TAG"
            docker logout ghcr.io
          '''
        }
      }
    }

    // Etapas 9-12: despliegue, verificación, prueba de humo y reversión automática.
    stage('Despliegue y verificación') {
      when { branch 'main' }
      steps {
        withCredentials([file(credentialsId: 'kubeconfig-k3s', variable: 'KUBECONFIG')]) {
          sh '''
            sed "s|__IMAGE__|$IMAGE_REPO:$IMAGE_TAG|" k8s/deployment.yaml > deployment.rendered.yaml
            kubectl apply -f k8s/configmap.yaml -f k8s/service.yaml -f k8s/ingress.yaml
            kubectl apply -f deployment.rendered.yaml
            kubectl -n "$NAMESPACE" annotate deployment/medisur-api \
              kubernetes.io/change-cause="build $BUILD_NUMBER - $IMAGE_TAG" --overwrite
          '''
          script {
            try {
              // Etapa 10: si los pods no quedan listos en 120 s, falla.
              sh 'kubectl -n "$NAMESPACE" rollout status deployment/medisur-api --timeout=120s'
              // Etapa 11: prueba de humo contra el servicio desplegado.
              sh '''
                curl -fsS --retry 5 --retry-delay 3 "http://$K8S_HOST/health"
                curl -fsS "http://$K8S_HOST/version" | tee version.json
                grep -q "$GIT_SHA" version.json
              '''
            } catch (err) {
              // Etapa 12: reversión automática y pipeline en rojo.
              sh 'kubectl -n "$NAMESPACE" rollout undo deployment/medisur-api'
              sh 'kubectl -n "$NAMESPACE" rollout status deployment/medisur-api --timeout=120s'
              error("Despliegue fallido; se revirtió a la versión anterior: ${err}")
            }
          }
        }
      }
    }
  }

  post {
    always {
      sh 'docker image prune -af --filter "until=48h" || true'
    }
  }
}