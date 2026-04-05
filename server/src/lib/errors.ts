import type { ContentfulStatusCode } from "hono/utils/http-status";
import type { ErrorHandler } from "hono";
import { logger } from "@/lib/logger";

export class AppError extends Error {
  statusCode: number;
  constructor(message: string, statusCode: number = 500) {
    super(message);
    this.statusCode = statusCode;
  }
}

export class NotFoundError extends AppError {
  constructor(message = "Resource not found") {
    super(message, 404);
  }
}

export class ValidationError extends AppError {
  constructor(message = "Validation failed") {
    super(message, 422);
  }
}

export class AuthenticationError extends AppError {
  constructor(message = "Authentication failed") {
    super(message, 401);
  }
}

export class ForbiddenError extends AppError {
  constructor(message = "Forbidden") {
    super(message, 403);
  }
}

export class BadRequestError extends AppError {
  constructor(message = "Bad request") {
    super(message, 400);
  }
}

export class ConflictError extends AppError {
  constructor(message = "Resource already modified") {
    super(message, 409);
  }
}

export const errorHandler: ErrorHandler = (err, c) => {
  if (err instanceof AppError) {
    return c.json(
      { detail: err.message },
      err.statusCode as ContentfulStatusCode,
    );
  }
  logger.error({ err }, "Unhandled error");
  return c.json({ detail: "Internal server error" }, 500);
};
