ARG BUILD_FROM
FROM ${BUILD_FROM}

WORKDIR /app

RUN apk add --no-cache \
      curl \
      tzdata \
    && python3 -m pip install --no-cache-dir \
      Flask==3.1.1 \
      gunicorn==23.0.0 \
      requests==2.32.4

COPY app /app
COPY run.sh /run.sh

RUN chmod a+x /run.sh \
    && mkdir -p /config/images

EXPOSE 8099

CMD ["/run.sh"]
