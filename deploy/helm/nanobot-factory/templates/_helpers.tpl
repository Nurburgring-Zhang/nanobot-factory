{{/*
Expand the name of the chart.
*/}}
{{- define "nanobot-factory.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "nanobot-factory.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Chart label string.
*/}}
{{- define "nanobot-factory.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels (applied to every resource).
Usage: {{ include "nanobot-factory.labels" . }}
*/}}
{{- define "nanobot-factory.labels" -}}
helm.sh/chart: {{ include "nanobot-factory.chart" . }}
{{ include "nanobot-factory.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: nanobot-factory
{{- end -}}

{{/*
Selector labels (used by Deployment / Service / HPA / PDB selectors).
Usage: {{ include "nanobot-factory.selectorLabels" . }}
*/}}
{{- define "nanobot-factory.selectorLabels" -}}
app.kubernetes.io/name: {{ include "nanobot-factory.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: backend
{{- end -}}

{{/*
ServiceAccount name.
*/}}
{{- define "nanobot-factory.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "nanobot-factory.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Image reference.
*/}}
{{- define "nanobot-factory.image" -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end -}}