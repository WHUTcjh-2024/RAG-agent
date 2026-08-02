# 第一阶段生产化改造实施计划

> 供执行者使用：逐项勾选任务；每个任务均先写失败测试，再实现，再验证与提交。

**目标：** 让 Java 网关可在 Ubuntu 虚拟机用 Docker Compose 连接 PostgreSQL 与 Redis，并提供健康检查、Prometheus 指标和安全配置。

**架构：** 把当前单一配置分为公共配置、local H2 配置、prod PostgreSQL/Redis 配置。订单列表通过缓存适配器使用 Spring Cache，缓存异常时回退 PostgreSQL。根 Compose 保留现有 Python backend 与前端服务块不变，只增加 PostgreSQL、Redis 并调整 Java 服务。

**技术栈：** Java 17、Spring Boot 3.3.5、JPA、Flyway、PostgreSQL、Redis、Spring Cache、Micrometer Prometheus、Docker Compose。

## 全局约束

- 不修改 backend/ 下的 Python RAG 代码、依赖、接口或 Compose 的 backend 服务定义。
- 本地和 Maven 测试使用 H2 与 local Profile，不依赖 Docker 或 Redis。
- 数据库、Redis、RAG 地址、JWT 密钥只从环境变量读取；不提交真实密码或私有地址。
- PostgreSQL 是用户、购物车、订单的唯一事实来源；Redis 只缓存可失效的读取数据。
- 创建或取消订单后，必须清除当前用户的订单列表缓存。
- 生产环境保持 spring.jpa.hibernate.ddl-auto=validate，表结构变更只由 Flyway 执行。

---

## Task 1: 配置分层、依赖与 Prometheus 指标

**文件：**
- 修改：java-backend/pom.xml
- 修改：java-backend/src/main/resources/application.yml
- 新建：java-backend/src/main/resources/application-local.yml
- 新建：java-backend/src/main/resources/application-prod.yml
- 新建：java-backend/src/test/java/com/atelier/gateway/health/ActuatorIntegrationTest.java

**接口：**
- 输入：现有 H2、Flyway、JPA、Gateway 配置。
- 输出：默认 local Profile、SPRING_PROFILES_ACTIVE=prod 可启用的 PostgreSQL/Redis 配置，以及 /actuator/prometheus。

- [ ] **Step 1：写失败的指标端点测试**

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ActuatorIntegrationTest {
    @Autowired
    private WebTestClient webTestClient;

    @Test
    void exposesPrometheusButNotEnvironmentValues() {
        webTestClient.get().uri("/actuator/prometheus").exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_PLAIN)
            .expectBody(String.class).value(body -> assertThat(body).contains("jvm_info"));

        webTestClient.get().uri("/actuator/env").exchange()
            .expectStatus().isNotFound();
    }
}
~~~

- [ ] **Step 2：运行测试确认失败**

运行：

~~~powershell
cd D:\727push\.worktrees\feature-production-readiness\java-backend
mvn -Dtest=ActuatorIntegrationTest test
~~~

预期：/actuator/prometheus 返回 404，因为未加入 Prometheus registry 且端点未暴露。

- [ ] **Step 3：添加最小生产依赖与配置**

在 pom.xml 添加：

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>org.flywaydb</groupId>
    <artifactId>flyway-database-postgresql</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

把 application.yml 改为公共 Gateway、Flyway、JPA、管理端点配置，并保留：

~~~yaml
spring:
  application:
    name: atelier-java-backend
  profiles:
    default: local
  cache:
    cache-names: orderLists

management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
~~~

application-local.yml 放入现在的 127.0.0.1、文件型 H2、默认本地 JWT 与本地 RAG 配置，另加：

~~~yaml
spring:
  cache:
    type: simple
~~~

创建 application-prod.yml：

~~~yaml
server:
  address: ${SERVER_ADDRESS:0.0.0.0}
  port: ${SERVER_PORT:8080}

rag:
  upstream-base-url: ${RAG_UPSTREAM_BASE_URL}

auth:
  jwt:
    secret: ${AUTH_JWT_SECRET}
    access-token-ttl: 2h

spring:
  datasource:
    url: ${SPRING_DATASOURCE_URL}
    driver-class-name: org.postgresql.Driver
    username: ${SPRING_DATASOURCE_USERNAME}
    password: ${SPRING_DATASOURCE_PASSWORD}
  data:
    redis:
      host: ${SPRING_DATA_REDIS_HOST}
      port: ${SPRING_DATA_REDIS_PORT:6379}
      password: ${SPRING_DATA_REDIS_PASSWORD}
  cache:
    type: redis
  jpa:
    hibernate:
      ddl-auto: validate
~~~

- [ ] **Step 4：运行测试确认通过**

运行：

~~~powershell
cd D:\727push\.worktrees\feature-production-readiness\java-backend
mvn -Dtest=ActuatorIntegrationTest test
~~~

预期：Maven 成功；Prometheus 输出包含 jvm_info，环境端点为 404。

- [ ] **Step 5：提交**

~~~powershell
git add java-backend/pom.xml java-backend/src/main/resources/application.yml java-backend/src/main/resources/application-local.yml java-backend/src/main/resources/application-prod.yml java-backend/src/test/java/com/atelier/gateway/health/ActuatorIntegrationTest.java
git commit -m "feat: 添加生产环境数据库缓存与指标配置"
~~~

## Task 2: 订单列表 Redis 缓存与失效

**文件：**
- 修改：java-backend/src/main/java/com/atelier/gateway/JavaBackendApplication.java
- 新建：java-backend/src/main/java/com/atelier/gateway/order/OrderListCache.java
- 修改：java-backend/src/main/java/com/atelier/gateway/order/OrderResponses.java
- 修改：java-backend/src/main/java/com/atelier/gateway/order/OrderService.java
- 修改：java-backend/src/test/java/com/atelier/gateway/order/OrderControllerIntegrationTest.java

**接口：**
- 输入：OrderRepository.findByUserIdOrderByCreatedAtDesc(UUID)、OrderResponses.OrderListView、CacheManager。
- 输出：OrderListCache 的 get(UUID)、put(UUID, OrderListView)、evict(UUID) 方法。

- [ ] **Step 1：写订单缓存失效测试**

在 OrderControllerIntegrationTest 注入 CacheManager；每次清理数据后调用：

~~~java
cacheManager.getCache("orderLists").clear();
~~~

添加下列测试，并另加一个“列表缓存后取消订单，重新查询返回 CANCELLED”的测试：

~~~java
@Test
void creatingOrderEvictsTheCurrentUsersCachedOrderList() {
    String token = registerAndToken("cache-create@example.com");
    webTestClient.get().uri("/api/orders").header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
        .exchange().expectStatus().isOk().expectBody().jsonPath("$.orders.length()").isEqualTo(0);

    addItem(token, "sku-cache", "Cache Coat", "/media/cache.png", "88.00", 1, true)
        .expectStatus().isOk();
    createOrder(token, "cache-create-001").expectStatus().isOk();

    webTestClient.get().uri("/api/orders").header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
        .exchange().expectStatus().isOk().expectBody().jsonPath("$.orders.length()").isEqualTo(1);
}
~~~

- [ ] **Step 2：运行测试确认失败**

运行：

~~~powershell
cd D:\727push\.worktrees\feature-production-readiness\java-backend
mvn -Dtest=OrderControllerIntegrationTest#creatingOrderEvictsTheCurrentUsersCachedOrderList test
~~~

预期：失败，因为创建订单不会清除缓存中的空订单列表。

- [ ] **Step 3：实现可降级缓存**

在 JavaBackendApplication 添加 @EnableCaching。

OrderListView 与 OrderSummaryView 必须实现 Serializable，保证 Redis 默认序列化可读取：

~~~java
public record OrderListView(List<OrderSummaryView> orders) implements Serializable {
}

public record OrderSummaryView(
    UUID id,
    OrderStatus status,
    BigDecimal totalAmount,
    Instant createdAt,
    Instant updatedAt
) implements Serializable {
    // 保留现有 from(Order order) 工厂方法。
}
~~~

创建 OrderListCache。所有缓存异常都必须被吞掉：读失败返回 Optional.empty()，写入与删除失败直接返回，使订单写入继续交给 PostgreSQL。

~~~java
@Service
public class OrderListCache {
    private static final String CACHE_NAME = "orderLists";
    private final CacheManager cacheManager;

    public OrderListCache(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    public Optional<OrderListView> get(UUID userId) {
        try {
            Cache.ValueWrapper value = cache().get(userId);
            return value == null ? Optional.empty() : Optional.of((OrderListView) value.get());
        } catch (RuntimeException ex) {
            return Optional.empty();
        }
    }

    public void put(UUID userId, OrderListView view) {
        try { cache().put(userId, view); } catch (RuntimeException ignored) { }
    }

    public void evict(UUID userId) {
        try { cache().evict(userId); } catch (RuntimeException ignored) { }
    }

    private Cache cache() {
        return Objects.requireNonNull(cacheManager.getCache(CACHE_NAME));
    }
}
~~~

在 OrderService.currentOrders 中依次：解析用户、尝试 get、未命中则查询 Repository、构建 OrderListView、put、返回。在 createOrder 成功创建新订单后和 cancelOrder 保存后调用 evict(userId)。

- [ ] **Step 4：运行订单测试确认通过**

~~~powershell
cd D:\727push\.worktrees\feature-production-readiness\java-backend
mvn -Dtest=OrderControllerIntegrationTest test
~~~

预期：Maven 成功；创建或取消订单后不会读到过期列表。

- [ ] **Step 5：提交**

~~~powershell
git add java-backend/src/main/java/com/atelier/gateway/JavaBackendApplication.java java-backend/src/main/java/com/atelier/gateway/order/OrderListCache.java java-backend/src/main/java/com/atelier/gateway/order/OrderResponses.java java-backend/src/main/java/com/atelier/gateway/order/OrderService.java java-backend/src/test/java/com/atelier/gateway/order/OrderControllerIntegrationTest.java
git commit -m "feat: 为订单列表添加可失效缓存"
~~~

## Task 3: Compose 中加入 PostgreSQL、Redis 与 Java 健康检查

**文件：**
- 修改：docker-compose.yml
- 修改：java-backend/Dockerfile
- 修改：.env.example

**接口：**
- 输入：application-prod.yml 的 SPRING_DATASOURCE、SPRING_DATA_REDIS、AUTH_JWT_SECRET，及现有 backend 服务名。
- 输出：postgres、redis、使用 prod Profile 的 java-backend 服务。

- [ ] **Step 1：确认当前 Compose 的缺口**

~~~powershell
cd D:\727push\.worktrees\feature-production-readiness
Copy-Item .env.example .env
docker compose config
~~~

预期：当前输出没有 postgres 和 redis，java-backend 仍引用 H2。

- [ ] **Step 2：让 Java 镜像能执行 HTTP 健康检查**

在 Java Dockerfile 的 JRE 阶段增加：

~~~dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
~~~

该变更只用于 Java 自身的 Actuator 健康检查，不修改 Python 镜像。

- [ ] **Step 3：扩展 Compose，保持 backend 与 frontend 服务块不变**

新增 PostgreSQL：

~~~yaml
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 10s
      timeout: 5s
      retries: 10
~~~

新增 Redis：

~~~yaml
  redis:
    image: redis:7-alpine
    command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}"]
    healthcheck:
      test: ["CMD-SHELL", "redis-cli -a \"$$REDIS_PASSWORD\" ping | grep PONG"]
      interval: 10s
      timeout: 5s
      retries: 10
~~~

把 java-backend 的环境变量改为：

~~~yaml
      SPRING_PROFILES_ACTIVE: prod
      SERVER_ADDRESS: 0.0.0.0
      RAG_UPSTREAM_BASE_URL: http://backend:18000
      AUTH_JWT_SECRET: ${AUTH_JWT_SECRET}
      SPRING_DATASOURCE_URL: jdbc:postgresql://postgres:5432/${POSTGRES_DB}
      SPRING_DATASOURCE_USERNAME: ${POSTGRES_USER}
      SPRING_DATASOURCE_PASSWORD: ${POSTGRES_PASSWORD}
      SPRING_DATA_REDIS_HOST: redis
      SPRING_DATA_REDIS_PORT: 6379
      SPRING_DATA_REDIS_PASSWORD: ${REDIS_PASSWORD}
~~~

给 java-backend 加入 backend 的 service_started 依赖、postgres 与 redis 的 service_healthy 依赖，并加：

~~~yaml
    healthcheck:
      test: ["CMD-SHELL", "curl --fail --silent http://localhost:8080/actuator/health || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 10
~~~

文件末尾添加 postgres-data 命名卷。在 .env.example 添加 POSTGRES_DB、POSTGRES_USER、POSTGRES_PASSWORD、REDIS_PASSWORD 的示例值，并保留 AUTH_JWT_SECRET 示例值。

- [ ] **Step 4：验证 Compose 语法**

~~~powershell
cd D:\727push\.worktrees\feature-production-readiness
Copy-Item .env.example .env
docker compose config
Remove-Item .env
~~~

预期：postgres、redis、java-backend 均可渲染，backend 与 frontend 仍存在，.env 未被 Git 跟踪。

- [ ] **Step 5：提交**

~~~powershell
git add docker-compose.yml java-backend/Dockerfile .env.example
git commit -m "feat: 添加 Java 生产环境 Compose 依赖"
~~~

## Task 4: 中文文档、全量测试与 Ubuntu 验收

**文件：**
- 修改：java-backend/README.md
- 修改：README.md

**接口：**
- 输入：Compose 服务名、.env.example、Profile 配置、Actuator 地址。
- 输出：本地开发、Ubuntu 部署、故障检查的中文说明。

- [ ] **Step 1：更新文档**

Java README 写入本地开发和 Ubuntu 虚拟机部署，必须包含：

~~~bash
git pull --ff-only
cp .env.example .env
# 编辑 .env，设置 POSTGRES_PASSWORD、REDIS_PASSWORD、AUTH_JWT_SECRET
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8080/actuator/health
curl http://127.0.0.1:8080/actuator/prometheus
~~~

根 README 必须说明：Python RAG 由 Python 负责人维护；本分支只维护 Java、PostgreSQL、Redis 与部署编排；.env 绝不能提交；Java 仍通过 http://backend:18000 访问 RAG。

- [ ] **Step 2：完整 Java 测试与敏感信息检查**

~~~powershell
cd D:\727push\.worktrees\feature-production-readiness\java-backend
mvn test

cd D:\727push\.worktrees\feature-production-readiness
git diff main --check
git status --short
~~~

预期：Maven 退出码为 0；没有空白错误、.env、真实密码或私有 IP。

- [ ] **Step 3：虚拟机启动和端点验证**

在 Ubuntu 虚拟机：

~~~bash
git fetch origin feature/production-readiness
git switch feature/production-readiness
git pull --ff-only origin feature/production-readiness
cp .env.example .env
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:8080/actuator/health
curl --fail http://127.0.0.1:8080/actuator/prometheus | head
~~~

预期：postgres、redis、java-backend 为健康或运行中；backend 与 frontend 保持运行；健康端点返回 UP，指标为 Prometheus 文本。

- [ ] **Step 4：验证 PostgreSQL 与 Redis 回退**

用现有 Java 注册、登录、购物车、下单接口创建订单，然后：

~~~bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT id, status, total_amount FROM orders;"
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" --scan --pattern 'orderLists*'
docker compose stop redis
# 令 TOKEN 为刚才登录接口返回的 accessToken
curl --fail -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/orders
docker compose start redis
~~~

预期：PostgreSQL 查询到 PENDING_PAYMENT 订单；Redis 可观察到订单缓存键；Redis 停止后订单查询仍返回 200 并回退 PostgreSQL。

- [ ] **Step 5：提交文档**

~~~powershell
git add java-backend/README.md README.md
git commit -m "docs: 补充 Java 生产环境部署说明"
~~~
