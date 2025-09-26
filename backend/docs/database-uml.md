# Diagramme UML de la base de données

Ce diagramme UML détaille l'intégralité du modèle relationnel du backend. Il comprend les attributs principaux de chaque entité ainsi que les cardinalités entre elles. Les attributs hérités de `BaseModel` (identifiant UUID et métadonnées temporelles) sont indiqués une seule fois pour alléger la lecture.

```plantuml
@startuml
hide methods
skinparam classAttributeIconSize 0
skinparam wrapWidth 240
skinparam maxMessageSize 240

abstract class BaseModel {
  +id: UUID (PK)
  +created_at: DateTime
  +updated_at: DateTime
}

class User {
  +email: EmailField [unique]
  +first_name: CharField
  +last_name: CharField
  +phone_number: CharField
  +date_of_birth: DateField?
  +email_verified: BooleanField
  +password_hash: CharField
  +is_active: BooleanField
  +is_staff: BooleanField
  +account_type: AccountType
}

class AgentProfile {
  +display_name: CharField
  +bio: TextField
}

class Organisation {
  +name: CharField
  +sector: CharField
  +size: Size
  +budget_min: DecimalField
  +budget_max: DecimalField
  +logo: ImageField?
  +country: CharField
  +description: TextField
  +website: URLField?
}

class Collaborator {
  +role: Role
  +job_title: CharField
}

class Sport {
  +name: CharField [unique]
  +discipline: CharField
}

class Athlete {
  +full_name: CharField
  +birth_date: DateField
  +nationality: CharField
  +bio: TextField
  +social_links: JSONField
  +is_self_represented: BooleanField
  +followers_count_cached: PositiveIntegerField
  +engagement_rate_cached: DecimalField
  +avatar: ImageField?
}

class ClauseTemplate {
  +identifier: CharField [unique]
  +title: CharField
  +type: ClauseType
  +content: TextField
  +placeholders: JSONField
  +mandatory: BooleanField
  +version: PositiveIntegerField
  +is_active: BooleanField
}

class Contract {
  +status: Status
  +start_date: DateField?
  +end_date: DateField?
  +amount: DecimalField
  +currency: CharField
}

class ContractClause {
  +values: JSONField
  +order_index: PositiveIntegerField
}

class ContractVersion {
  +version_number: PositiveIntegerField
  +snapshot: JSONField
}

class ContractStatusHistory {
  +from_status: Status?
  +to_status: Status
  +changed_at: DateTime
  +reason: TextField
}

class Notification {
  +type: Type
  +payload: JSONField
  +is_read: BooleanField
}

class Follow {
  +notify_news: BooleanField
  +notify_stats: BooleanField
  +notify_contracts: BooleanField
}

class Thread {
  +last_message_at: DateTime?
}

class Message {
  +content: TextField
  +attachment: FileField?
  +is_read: BooleanField
}

class SocialPlatform {
  +name: Platform [unique]
  +base_url: URLField?
}

class AthleteSocialAccount {
  +username: CharField
  +external_id: CharField [unique]
  +access_token: TextField?
  +is_active: BooleanField
}

class DailyStats {
  +date: DateField
  +followers: PositiveIntegerField
  +following: PositiveIntegerField?
  +posts_count: PositiveIntegerField
  +likes: PositiveIntegerField
  +comments: PositiveIntegerField
  +shares: PositiveIntegerField?
  +views: PositiveIntegerField?
  +watch_time: FloatField?
  +engagement_rate: FloatField
  +top_post: JSONField?
}

class SubscriptionPlan {
  +code: CharField [unique]
  +name: CharField
  +price: DecimalField
  +currency: CharField
  +max_athletes: PositiveIntegerField
  +max_collaborators: PositiveIntegerField
  +features: JSONField
  +stripe_product_id: CharField?
  +stripe_price_id: CharField?
  +is_active: BooleanField
}

class Subscription {
  +status: Status
  +start_at: DateTime
  +current_period_end: DateTime
  +stripe_customer_id: CharField?
  +stripe_subscription_id: CharField?
}

BaseModel <|-- User
BaseModel <|-- AgentProfile
BaseModel <|-- Organisation
BaseModel <|-- Collaborator
BaseModel <|-- Sport
BaseModel <|-- Athlete
BaseModel <|-- ClauseTemplate
BaseModel <|-- Contract
BaseModel <|-- ContractClause
BaseModel <|-- ContractVersion
BaseModel <|-- ContractStatusHistory
BaseModel <|-- Notification
BaseModel <|-- Follow
BaseModel <|-- Thread
BaseModel <|-- Message
BaseModel <|-- SocialPlatform
BaseModel <|-- AthleteSocialAccount
BaseModel <|-- DailyStats
BaseModel <|-- SubscriptionPlan
BaseModel <|-- Subscription

User "1" -- "0..1" AgentProfile : agent_profile
User "1" o-- "0..*" Organisation : owner
User "1" o-- "0..*" Collaborator : user
User "1" o-- "0..*" ContractStatusHistory : changed_by
User "1" o-- "0..*" Message : sender
User "1" o-- "0..*" Notification : notifications

AgentProfile "1" -- "0..*" Athlete : agent
AgentProfile "1" -- "0..*" Thread : threads
AgentProfile "1" -- "0..*" Subscription : subscriptions

Organisation "1" -- "1..*" Collaborator : collaborators
Organisation "1" -- "0..*" Contract : contracts
Organisation "1" -- "0..*" Subscription : subscriptions

Collaborator "1" -- "0..*" Contract : created_contracts
Collaborator "1" -- "0..*" Follow : follows
Collaborator "1" -- "0..*" Thread : threads

Sport "1" -- "0..*" Athlete : athletes

Athlete "1" -- "0..*" Contract : contracts
Athlete "1" -- "0..*" Follow : follows
Athlete "1" -- "0..*" Thread : threads
Athlete "1" -- "0..*" AthleteSocialAccount : social_accounts

ClauseTemplate "1" -- "0..*" ContractClause : contract_clauses

Contract "1" -- "0..*" ContractClause : clauses
Contract "1" -- "0..*" ContractVersion : versions
Contract "1" -- "0..*" ContractStatusHistory : status_history

SocialPlatform "1" -- "0..*" AthleteSocialAccount : accounts

AthleteSocialAccount "1" -- "0..*" DailyStats : daily_stats

SubscriptionPlan "1" -- "0..*" Subscription : subscriptions

note "Une souscription est liée soit à une organisation, soit à un agent (contrainte XOR)." as N1
Subscription .. N1

@enduml
```

> 💡 **Astuce :** pour visualiser le diagramme, copiez le bloc PlantUML ci-dessus dans un rendu compatible (PlantUML, Kroki, etc.).
