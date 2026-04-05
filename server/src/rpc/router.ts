import { auth } from "./auth";
import { project } from "./project";
import { document } from "./document";
import { skill } from "./skill";
import { server } from "./server";
import { service } from "./service";
import { connection } from "./connection";
import { notification } from "./notification";
import { version } from "./version";

export const router = {
  auth,
  project,
  document,
  skill,
  server,
  service,
  connection,
  notification,
  version,
};

export type AppRouter = typeof router;
