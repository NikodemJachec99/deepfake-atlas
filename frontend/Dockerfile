# Obraz z publicznego lustra ECR: ten sam oficjalny obraz Node, bez limitu pobrań Docker Huba.
# NODE_IMAGE pozwala przejść na Docker Hub, gdy ECR odmawia (429, wyczerpany limit danych).
ARG NODE_IMAGE=public.ecr.aws/docker/library/node:24-alpine
FROM ${NODE_IMAGE} AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM ${NODE_IMAGE}
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "run", "start"]
