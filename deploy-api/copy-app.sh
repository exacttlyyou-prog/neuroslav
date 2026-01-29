#!/bin/sh
# Копируем apps/api/app в deploy-api/app — в бандле Vercel симлинк не раскрывается
cp -r ../apps/api/app ./app
