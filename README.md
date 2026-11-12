# Apigee Edge MCP Server

![Apigee logo](assets/apigee-source.png)

**Created:** 12 November 2026 · [TheMackemNerd](https://github.com/TheMackemNerd)

A [FastMCP](https://github.com/jlowin/fastmcp) server that exposes the [Apigee Edge Management API](https://docs.apigee.com/api-platform/system-administration/management-api-tokens) as MCP tools for AI clients (Cursor, Claude Desktop, and others).

> **Disclaimer:** This project has only been tested against **Apigee Edge**. Compatibility with **Apigee X** or **Apigee hybrid** has not been verified.

## Credentials (`.env`)

1. Copy [`.env.example`](.env.example) to `.env` in the project root.
2. Set at least:
   - `APIGEE_USERNAME` — Apigee account email
   - `APIGEE_PASSWORD` — account password
3. Set `APIGEE_ORG` to your organization name (recommended). When set, tools default the `ORG` path parameter to that value, and `ListOrganizations` is omitted (that call often returns 403 for org-scoped users).
4. Optional: `APIGEE_TOKEN_URL` (SAML zone URL if required), `APIGEE_MFA_TOKEN`, and related settings documented in `.env.example`.

The Apigee user in `.env` must exist on the target organization with the **Organization Administrator** role. Without that role, many Management API calls will fail with 403.

Do not put credentials in client MCP config files — keep them in `.env` (or your process environment) only.

## Running locally

Install the package (see [`pyproject.toml`](pyproject.toml)), load your `.env` values into the environment, and start the server:

```bash
pip install -e .
python -m apigee_mcp.server
```

You can also run it under Docker or any other process manager that can supply the same environment variables. Exact wiring depends on your OS and MCP client — use whatever approach fits your setup.

By default the server serves Streamable HTTP MCP (see env vars such as `FASTMCP_HOST`, `FASTMCP_PORT`, and `FASTMCP_PATH` in the source). Point your MCP client at the `/mcp` endpoint once the process is up.

## Warning

The OpenAPI surface includes **destructive** Management API operations (delete, undeploy, credential changes, and similar). Prefer a non-production org for experimentation, and review tool calls before approving them in your client.

## MCP tools

Tools are generated from [`openapi/openapi.yaml`](openapi/openapi.yaml). When `APIGEE_ORG` is set, `ListOrganizations` is not registered.

| Tool | Summary |
|------|---------|
| `ListDeployments` | List deployments for an organization |
| `UserRolesUpdate` | Update user roles |
| `DeleteAnOrganizationUserrole` | Delete an organization user role |
| `Oauth2TokenDetailsGet` | Get OAuth2 access token details |
| `KvmGet` | Get a key-value map |
| `KvmDeleteEntireKvm` | Delete an entire key-value map |
| `AnalyticsPod` | Analytics pod operations |
| `Deregister` | Deregister a server |
| `GetDevelopers` | List developers |
| `CreateDeveloper` | Create a developer |
| `ApiList` | List API proxies |
| `DeployApi` | Deploy an API proxy revision |
| `GetAssociatedPods` | List pods associated with the organization |
| `DisassociateOrgFromPod` | Disassociate the organization from a pod |
| `ListCaches` | List caches in an environment |
| `Audit` | Audit organization companies |
| `DeveloperDetailsGet` | Get developer details |
| `ListServerByUuid` | List a server by UUID |
| `ClusterStatus` | Get cluster status |
| `DeleteAnApi` | Delete an API proxy |
| `EnableDebugWithoutRestart` | Enable debug without restart |
| `CreateCompanyApp` | Create a company app |
| `CreateUserInOrg` | Create a user in the organization |
| `ListUsers` | List organization users |
| `ListVirtualhosts` | List virtual hosts |
| `AddVirtualHost` | Add a virtual host |
| `SetNotReachable` | Mark a server as not reachable |
| `Deployments` | Get deployments for an API revision |
| `UndeployRevisions` | Undeploy an API revision |
| `ListOrgEnvServers` | List servers for an org/environment |
| `RegisterServerWithOrg` | Register a server with the organization |
| `UpdateEnvironments` | Update an environment |
| `DeleteEnvironment` | Delete an environment |
| `AddAppCredentials` | Add app credentials |
| `CreateCompanyDeveloper` | Create a company developer |
| `AssociateEnvironmentsToMp` | Associate environments with a message processor |
| `DeveloperAppDetailsGet` | Get developer app details |
| `DeleteAppCredentials` | Delete app credentials |
| `CreateNewEnvInOrg` | Create a new environment |
| `ListKeystores` | List keystores |
| `GetPermissionsForARole` | Get permissions for a role |
| `ApiProducts` | List API products |
| `ApiproductCreation` | Create an API product |
| `ListTargetServers` | List target servers |
| `AddTarget` | Add a target server |
| `CreateCompany` | Create a company |
| `DisableDebugWithoutRestart` | Disable debug without restart |
| `AddUserAsOrgadmin` | Add a user as orgadmin |
| `ListApps` | List apps |
| `ListApp` | Get a single app |
| `ListOrganizations` | List organizations (omitted when `APIGEE_ORG` is set) |

## License

MIT — see [LICENSE](LICENSE).
