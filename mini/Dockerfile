FROM --platform=linux/arm64 ubuntu:20.04 as builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    openjdk-11-jdk \
    maven \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/logicalclocks/hopsworks.git /hopsworks

WORKDIR /hopsworks

RUN mvn clean install -DskipTests

FROM --platform=linux/arm64 ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    openjdk-11-jre \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /hopsworks/hopsworks-ear/target/hopsworks-ear.ear /hopsworks/hopsworks-ear.ear

EXPOSE 8080

CMD ["java", "-jar", "/hopsworks/hopsworks-ear.ear"]