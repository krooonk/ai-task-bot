FROM node:20-alpine

WORKDIR /app

# Install dependencies first for better caching
COPY package*.json ./
RUN npm install

# Copy the rest of the frontend files
COPY . .

EXPOSE 3000

# Run Vite dev server bound to all network interfaces
CMD ["npm", "run", "dev", "--", "--host"]