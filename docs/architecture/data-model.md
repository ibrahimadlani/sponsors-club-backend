# Diagramme UML de la base de données

Ce schéma couvre l'ensemble des modèles persistés dans Django pour l'application Sponsors Club. Il inclut les cardinalités, les champs principaux ainsi que les tables d'association.

```mermaid
classDiagram
    direction TB

    class User {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +email email (unique)
        +string first_name
        +string last_name
        +string phone_country_code?
        +string phone_number?
        +date date_of_birth?
        +bool email_verified
        +string password_hash
        +bool is_active
        +bool is_staff
        +string account_type
        +string password
        +datetime last_login?
        +bool is_superuser
    }

    class AgentProfile {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string display_name
        +text bio
        +bool is_self_represented
    }

    class EmailVerificationToken {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +char token_hash
        +datetime expires_at
        +datetime used_at?
    }

    class Organisation {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string name
        +slug slug (unique)
        +string type
        +string industry
        +image logo?
        +image banner_image?
        +text description
        +url website_url
        +email email_contact
        +string phone_contact
        +string address_city
        +string address_country
        +string address_postal_code
        +json social_links
        +int founded_year?
        +int employees_count?
        +string budget_range
        +json sponsoring_focus
    }

    class Collaborator {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string role
        +string job_title
    }

    class OrganisationInvite {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string code (unique)
        +datetime expires_at
        +bool is_used
        +datetime used_at?
    }

    class Sport {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string name (unique)
        +slug slug (unique)
        +string emoji?
        +string category
    }

    class SportDiscipline {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string name
        +slug slug
        +string description
        +bool is_olympic
    }

    class Athlete {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string full_name
        +slug slug (unique)
        +date birth_date
        +string nationality
        +string country
        +string city
        +text bio
        +json social_links
        +int followers_count_cached
        +decimal engagement_rate_cached
        +image avatar?
    }

    class AthleteDiscipline {
        +UUID id
        +datetime created_at
        +datetime updated_at
    }

    class AthletePhoto {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +image image
        +string caption
        +int position
    }

    class SocialPlatform {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string name (unique)
        +url base_url?
    }

    class AthleteSocialAccount {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string username
        +string external_id (unique)
        +text access_token?
        +bool is_active
    }

    class DailyStats {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +date date
        +int followers
        +int following?
        +int posts_count
        +int likes
        +int comments
        +int shares?
        +int views?
        +float watch_time?
        +float engagement_rate
        +json top_post?
    }

    class Follow {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +bool notify_news
        +bool notify_stats
        +bool notify_contracts
    }

    class SubscriptionPlan {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string code (unique)
        +string name
        +decimal price
        +string currency
        +int max_athletes
        +int max_collaborators
        +json features
        +string stripe_product_id
        +string stripe_price_id
        +bool is_active
    }

    class Subscription {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string status
        +datetime start_at
        +datetime current_period_end
        +string stripe_customer_id
        +string stripe_subscription_id
    }

    class Thread {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +datetime last_message_at?
    }

    class Message {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +text content
        +file attachment?
        +bool is_read
    }

    class Notification {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string type
        +json payload
        +bool is_read
    }

    class ClauseTemplate {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string category
        +string title
        +text content
        +json placeholders
        +bool is_mandatory
        +int version
    }

    class Contract {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string status
        +string title
        +date effective_date?
        +date expiration_date?
        +datetime owner_agreed_at?
        +datetime agent_agreed_at?
        +int current_version_number
    }

    class ContractClause {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string title
        +text content
        +bool is_mandatory
        +bool is_modified
    }

    class ContractRevision {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +text comment
        +bool accepted?
    }

    class ContractVersion {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +int number
        +text notes
    }

    class ContractComment {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +text body
    }

    class ContractLegalReview {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +text notes
        +datetime verified_at?
        +text verification_notes
    }

    class ContractSigning {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +string envelope_id
        +string status
        +json last_payload
        +datetime completed_at?
    }

    class ContractFile {
        +UUID id
        +datetime created_at
        +datetime updated_at
        +file pdf
    }

    User "1" -- "0..1" AgentProfile : agent_profile
    User ||--o{ EmailVerificationToken : email_tokens
    User "1" -- "0..*" Organisation : owner
    User "1" -- "0..*" Collaborator : user
    User "1" -- "0..*" OrganisationInvite : used_by
    User "1" -- "0..*" Message : sender
    User "1" -- "0..*" Notification : notifications
    User "1" -- "0..*" ContractRevision : proposed_by
    User "1" -- "0..*" ContractVersion : created_by
    User "1" -- "0..*" ContractComment : author
    User "1" -- "0..*" ContractLegalReview : requested_by / verified_by
    User "1" -- "0..*" ContractSigning : initiated_by

    Organisation ||--o{ Collaborator : collaborators
    Organisation ||--o{ OrganisationInvite : invites
    Organisation ||--o{ Contract : contracts
    Organisation ||--o{ Subscription : subscriptions

    Collaborator ||--o{ OrganisationInvite : created_invites
    Collaborator ||--o{ Follow : follows
    Collaborator ||--o{ Thread : threads
    Collaborator ||--o{ Contract : initiated_contracts

    AgentProfile ||--o{ Athlete : athletes
    AgentProfile ||--o{ Thread : threads
    AgentProfile ||--o{ Contract : contracts
    AgentProfile ||--o{ Subscription : subscriptions

    Sport ||--o{ SportDiscipline : disciplines
    Sport ||--o{ Athlete : athletes

    SportDiscipline ||--o{ AthleteDiscipline : discipline_links
    Athlete ||--o{ AthleteDiscipline : discipline_links
    Athlete ||--o{ AthletePhoto : photos
    Athlete ||--o{ AthleteSocialAccount : social_accounts
    Athlete ||--o{ Follow : follows
    Athlete ||--o{ Thread : threads

    AthleteDiscipline }|--|| SportDiscipline : discipline
    AthleteDiscipline }|--|| Athlete : athlete

    SocialPlatform ||--o{ AthleteSocialAccount : accounts
    AthleteSocialAccount ||--o{ DailyStats : daily_stats

    SubscriptionPlan ||--o{ Subscription : subscriptions

    Thread ||--o{ Message : messages
    Thread }o--|| Athlete : athlete

    Contract ||--o{ ContractClause : clauses
    Contract ||--o{ ContractRevision : revisions
    Contract ||--o{ ContractVersion : versions
    Contract ||--o{ ContractComment : comments
    Contract ||--|| ContractLegalReview : legal_review
    Contract ||--|| ContractSigning : signing
    Contract ||--|| ContractFile : file

    ContractClause ||--o{ ContractRevision : clauses_changed
    ContractClause ||--o{ ContractComment : comments

    ContractRevision ||--o{ ContractVersion : resulting_versions

    ContractVersion ||--o{ ContractComment : comments
    ContractVersion }o--|| ContractRevision : source_revision

    OrganisationInvite }o--|| User : used_by
    OrganisationInvite }|--|| Organisation : organisation
    OrganisationInvite }|--|| Collaborator : created_by

    Subscription }o--|| Organisation : organisation
    Subscription }o--|| AgentProfile : agent
    Subscription }|--|| SubscriptionPlan : plan

    Follow }|--|| Collaborator : collaborator
    Follow }|--|| Athlete : athlete

    Message }|--|| Thread : thread

    DailyStats }|--|| AthleteSocialAccount : account
```
```

## Points d'attention

- Les modèles héritent d'une base commune avec identifiants UUID et horodatages automatiques, ce qui facilite la réplication entre environnements. 【F:users/models.py†L19-L28】【F:athletes/models.py†L14-L33】
- Le modèle `Subscription` applique une contrainte XOR : une souscription est liée soit à une organisation soit à un agent, mais jamais aux deux simultanément. 【F:payments/models.py†L81-L124】
- Les révisions de contrats gèrent une relation plusieurs-à-plusieurs vers les clauses via `clauses_changed`, permettant de tracer précisément quelles dispositions ont été proposées puis versionnées. 【F:contracts/models.py†L123-L214】
- `User` hérite de `PermissionsMixin`, maintenant les relations Django natives avec les groupes et permissions (`auth_group`, `auth_permission`) ; elles ne sont pas détaillées ici mais restent disponibles dans la base. 【F:users/models.py†L8-L18】
