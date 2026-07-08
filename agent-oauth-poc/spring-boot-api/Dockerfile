# Multi-stage build para Spring Boot
# Etapa 1: build con Maven
FROM maven:3.9-eclipse-temurin-17 AS builder

WORKDIR /build

# Cache de dependencias primero (se invalida solo si cambia pom.xml)
COPY pom.xml .
RUN mvn dependency:go-offline -B || true

# Copiar código y compilar
COPY src ./src
RUN mvn clean package -DskipTests -B

# Etapa 2: runtime slim
FROM eclipse-temurin:17-jre-alpine

WORKDIR /app

# Copiar el JAR compilado
COPY --from=builder /build/target/*.jar app.jar

# Spring Boot usa el puerto 9090 (definido en application.yml)
EXPOSE 9090

# Healthcheck con curl (Alpine lo tiene por defecto en versiones recientes)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:9090/health || exit 1

# Argumentos JVM para reducir memoria en contenedores pequeños
ENV JAVA_OPTS="-Xms128m -Xmx512m"

# Lanzar la app
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar /app/app.jar"]