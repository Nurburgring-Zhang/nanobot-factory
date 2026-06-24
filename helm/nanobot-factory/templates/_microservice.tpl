{{- /*
microservice.yaml — single template that renders a Deployment + Service +
HPA for any of the 12 domain services.

Usage:
  {{- include "nanobot-factory.microservice" (dict
      "ctx" .
      "name" "user-service"
      "module" "backend.services.user_service.main"
      "port" 8001
      "heavy" false) }}
*/ -}}
{{- define "nanobot-factory.microservice" -}}
{{- $ctx := .ctx -}}
{{- $name := .name -}}
{{- $module := .module -}}
{{- $port := .port | int -}}
{{- $heavy := .heavy | default false -}}
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ $name }}
  namespace: nanobot-factory
  labels:
    {{- include "nanobot-factory.commonLabels" (dict "ctx" $ctx "name" $name) | nindent 4 }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ $name }}
  namespace: nanobot-factory
  labels:
    {{- include "nanobot-factory.commonLabels" (dict "ctx" $ctx "name" $name) | nindent 4 }}
spec:
  replicas: {{ $ctx.Values.replicas.default }}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      {{- include "nanobot-factory.selectorLabels" (dict "ctx" $ctx "name" $name) | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "nanobot-factory.commonLabels" (dict "ctx" $ctx "name" $name) | nindent 8 }}
    spec:
      serviceAccountName: {{ $name }}
      containers:
        - name: {{ $name }}
          image: {{ include "nanobot-factory.image" (dict "ctx" $ctx) }}
          imagePullPolicy: {{ $ctx.Values.image.pullPolicy }}
          command:
            - /opt/venv/bin/uvicorn
            - {{ $module }}:app
            - --host
            - 0.0.0.0
            - --port
            - {{ $port | quote }}
            - --log-level
            - info
          ports:
            - name: http
              containerPort: {{ $port }}
              protocol: TCP
          env:
            - name: NANOBOT_PORT
              value: {{ $port | quote }}
            - name: JWT_SECRET
              valueFrom:
                secretKeyRef:
                  name: {{ include "nanobot-factory.fullname" $ctx }}-secrets
                  key: JWT_SECRET
          envFrom:
            - configMapRef:
                name: {{ include "nanobot-factory.fullname" $ctx }}-config
          {{- include "nanobot-factory.resources" (dict "ctx" $ctx "heavy" $heavy) | nindent 10 }}
          livenessProbe:
            httpGet:
              path: /healthz
              port: {{ $port }}
            initialDelaySeconds: 25
            periodSeconds: 15
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /healthz
              port: {{ $port }}
            initialDelaySeconds: 10
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 3
---
apiVersion: v1
kind: Service
metadata:
  name: {{ $name }}
  namespace: nanobot-factory
  labels:
    {{- include "nanobot-factory.commonLabels" (dict "ctx" $ctx "name" $name) | nindent 4 }}
spec:
  type: ClusterIP
  ports:
    - name: http
      port: {{ $port }}
      targetPort: {{ $port }}
      protocol: TCP
  selector:
    {{- include "nanobot-factory.selectorLabels" (dict "ctx" $ctx "name" $name) | nindent 4 }}
---
{{- if $ctx.Values.autoscaling.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ $name }}
  namespace: nanobot-factory
  labels:
    {{- include "nanobot-factory.commonLabels" (dict "ctx" $ctx "name" $name) | nindent 4 }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ $name }}
  minReplicas: {{ $ctx.Values.autoscaling.minReplicas }}
  maxReplicas: {{ $ctx.Values.autoscaling.maxReplicas }}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ $ctx.Values.autoscaling.targetCPUUtilizationPercentage }}
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: {{ $ctx.Values.autoscaling.targetMemoryUtilizationPercentage }}
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 30
      policies:
        - type: Percent
          value: 100
          periodSeconds: 30
    scaleDown:
      stabilizationWindowSeconds: 300
{{- end }}
{{- end -}}