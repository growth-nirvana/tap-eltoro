"""Stream type classes for tap-eltoro."""

from __future__ import annotations

import sys
import typing as t
from datetime import datetime, timedelta
from importlib import resources

from singer_sdk import typing as th  # JSON Schema typing helpers

from tap_eltoro.client import ElToroStream

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if t.TYPE_CHECKING:
    from singer_sdk.helpers.types import Context

# TODO: Delete this is if not using json files for schema definition
SCHEMAS_DIR = resources.files(__package__) / "schemas"


class OrganizationsStream(ElToroStream):
    """El Toro Organizations stream for listing all available organizations."""

    name = "organizations"
    path = "/v1/orgs"
    
    @override
    @property
    def url_base(self) -> str:
        """Return the API URL root for organizations service."""
        # Organizations are on the hagrid subdomain, not platform
        environment = self.config.get("environment", "production")
        if environment == "development":
            return "https://hagrid.api.dev.eltoro.com"
        else:
            # For production, try without the 'dev' part
            return "https://hagrid.api.eltoro.com"
    primary_keys: t.ClassVar[list[str]] = ["id"]
    replication_key = "update_time"
    
    # Define the schema based on the API response structure
    schema = th.PropertiesList(
        # Core organization fields
        th.Property("id", th.StringType, description="ID of the Organization"),
        th.Property("name", th.StringType, description="Name associated with this Organization"),
        th.Property("parent_org_id", th.StringType, description="ID of the parent org"),
        th.Property("create_time", th.DateTimeType, description="Date and time that the org was created"),
        th.Property("update_time", th.DateTimeType, description="Date and time of the last update"),
        th.Property("delete_time", th.DateTimeType, description="Date and time that the org was deleted"),
        th.Property("status", th.StringType, description="Status of the Org"),
        th.Property("ref_id", th.StringType, description="Reference ID"),
        
        # Business configuration
        th.Property("reseller", th.BooleanType, description="Whether this is an authorized reseller Organization"),
        th.Property("prepay", th.BooleanType, description="Whether the org needs to prepay for orderlines"),
        th.Property("msa_signed", th.BooleanType, description="Whether the org has signed the MSA"),
        th.Property("billable_org_id", th.StringType, description="Whether an org is billable"),
        th.Property("initial_setup_fee", th.IntegerType, description="The fee for initial setup of the Org"),
        th.Property("setup_fee_paid", th.BooleanType, description="Whether the initial setup fee is paid"),
        th.Property("minimum_impressions", th.IntegerType, description="Minimum impressions requirement"),
        
        # Account status flags
        th.Property("accounting_hold", th.BooleanType, description="Ad-Ops Account Freeze"),
        th.Property("admin_accounting_hold", th.BooleanType, description="Administrative Account Suspension"),
        th.Property("billing_hold", th.BooleanType, description="Accounting Overdue Hold"),
        th.Property("override_credit_card_requirement", th.BooleanType, description="Override credit card requirement"),
        th.Property("override_prepay_balance", th.BooleanType, description="Override prepay balance"),
        th.Property("in_collections", th.BooleanType, description="Whether the Org is in collections"),
        th.Property("notifications_disabled", th.BooleanType, description="Whether org should receive notifications"),
        th.Property("is_active", th.BooleanType, description="Whether the org is active"),
        th.Property("web_to_home_enabled", th.BooleanType, description="Whether org is enabled for Web to Home"),
        th.Property("is_publisher", th.BooleanType, description="Whether org is enabled as a publisher"),
        
        # Metadata
        th.Property("time_zone", th.StringType, description="The time zone of the org"),
        th.Property("last_sync_time", th.DateTimeType, description="Date and time org was last synced from v2"),
        
        # Complex nested objects (simplified as JSON for now)
        th.Property("child_orgs", th.ArrayType(th.ObjectType()), description="List of child orgs"),
        th.Property("account_reps", th.ArrayType(th.ObjectType()), description="Account representatives"),
        th.Property("contacts", th.ArrayType(th.ObjectType()), description="User contacts"),
        th.Property("cpms", th.ObjectType(), description="CPM configuration"),
        th.Property("logo", th.ObjectType(), description="Organization logo"),
        th.Property("commission_group", th.ObjectType(), description="Commission group configuration"),
        th.Property("notes", th.ArrayType(th.ObjectType()), description="Organization notes"),
        
        # Additional fields found in API response
        th.Property("sales_rep_ids", th.ArrayType(th.StringType()), description="Sales representative IDs"),
        th.Property("user_ids", th.ArrayType(th.StringType()), description="User IDs associated with org"),
        th.Property("commission_group_id", th.StringType, description="Commission group ID"),
    ).to_dict()

    @override
    def get_url_params(
        self,
        context: Context | None,
        next_page_token: t.Any | None,
    ) -> dict[str, t.Any]:
        """Return URL parameters for pagination and filtering."""
        params: dict = {}
        
        # Add pagination
        if next_page_token:
            params["page_token"] = next_page_token
            
        # Set page size (max 100)
        params["page_size"] = min(self.config.get("page_size", 100), 100)
        
        # Add optional filtering and ordering
        if self.config.get("org_filter"):
            params["filter"] = self.config["org_filter"]
        if self.config.get("org_order_by"):
            params["order_by"] = self.config["org_order_by"]
            
        return params

    @override
    def parse_response(self, response: t.Any) -> t.Iterable[dict]:
        """Parse the organizations response and yield individual records."""
        data = response.json()
        
        # Get organization filter from config
        organization_ids = self.config.get("organization_ids")
        
        # Yield each organization
        if "orgs" in data:
            for org in data["orgs"]:
                # Filter organizations if organization_ids is specified
                if organization_ids and org["id"] not in organization_ids:
                    continue
                yield org

    @override
    def get_next_page_token(
        self, 
        response: t.Any, 
        previous_token: t.Any | None
    ) -> t.Any | None:
        """Extract next page token from response."""
        data = response.json()
        return data.get("next_page_token")

    @override
    def get_child_context(self, record: dict, context: Context | None) -> dict:
        """Generate context for child stream based on parent organization record."""
        return {
            "org_id": record["id"],
            "org_name": record.get("name", ""),
        }


class CampaignsStream(ElToroStream):
    """El Toro Campaigns stream for listing campaigns by organization."""

    name = "campaigns"
    path = "/v1/campaigns"
    primary_keys: t.ClassVar[list[str]] = ["id"]
    replication_key = "update_time"
    parent_stream_type = OrganizationsStream
    
    @override
    @property
    def url_base(self) -> str:
        """Return the API URL root for campaigns service (same as organizations/stats)."""
        # Campaigns are also on the hagrid subdomain
        environment = self.config.get("environment", "production")
        if environment == "development":
            return "https://hagrid.api.dev.eltoro.com"
        else:
            # For production, try without the 'dev' part
            return "https://hagrid.api.eltoro.com"
    
    # Define the schema based on the API response structure
    schema = th.PropertiesList(
        # Core campaign fields
        th.Property("id", th.StringType, description="ID of the Campaign"),
        th.Property("name", th.StringType, description="Name of the Campaign"),
        th.Property("org_id", th.StringType, description="Id of the org to which this campaign belongs"),
        
        # Timestamps
        th.Property("create_time", th.DateTimeType, description="Time Campaign was created"),
        th.Property("update_time", th.DateTimeType, description="Time Campaign was updated"),
        th.Property("delete_time", th.DateTimeType, description="Time Campaign was deleted"),
        th.Property("archive_time", th.DateTimeType, description="Time Campaign was archived"),
        th.Property("start_time", th.DateTimeType, description="Date the Campaign should start"),
        th.Property("end_time", th.DateTimeType, description="Date the Campaign should end"),
        
        # Status and metadata
        th.Property("status", th.StringType, description="The status of the campaign"),
        th.Property("ref_id", th.StringType, description="Client reference ID"),
        
        # Complex nested objects
        th.Property("order_lines", th.ArrayType(th.ObjectType()), description="Order lines associated with the campaign"),
        th.Property("political_transparency", th.ObjectType(), description="Political transparency information"),
        th.Property("job_id", th.StringType, description="Job ID"),
        th.Property("po_id", th.StringType, description="PO ID"),
    ).to_dict()
    
    @property
    def state_partitioning_keys(self) -> list[str] | None:
        """Return state partitioning keys for the stream."""
        return ["org_id"]
    
    @override
    def get_url_params(
        self, context: Context | None, next_page_token: t.Any | None
    ) -> dict[str, t.Any]:
        """Get URL parameters for the campaigns request."""
        params = {}
        
        # Add pagination
        if next_page_token:
            params["page_token"] = next_page_token
        
        # Set page size (up to 1000 max)
        params["page_size"] = 1000
        
        # Try to filter by org_id if we have it from context
        if context and "org_id" in context:
            # This might not work if the API doesn't support org_id filtering
            # We'll test this and fall back to client-side filtering if needed
            params["filter"] = f"org_id={context['org_id']}"
        
        return params
    
    @override
    def parse_response(self, response: t.Any, context: Context | None = None) -> t.Iterable[dict]:
        """Parse the campaigns response and yield individual records."""
        data = response.json()
        
        # Get org_id from context for filtering
        context_org_id = None
        if context and "org_id" in context:
            context_org_id = context["org_id"]
        
        # Parse campaigns
        if "campaigns" in data:
            for campaign in data["campaigns"]:
                # If we have a context org_id, filter campaigns to match
                if context_org_id and campaign.get("org_id") != context_org_id:
                    # Skip campaigns that don't belong to this org
                    continue
                
                yield campaign
    
    @override
    def get_next_page_token(
        self, 
        response: t.Any, 
        previous_token: t.Any | None
    ) -> t.Any | None:
        """Extract next page token from response."""
        data = response.json()
        return data.get("next_page_token")


class OrderLinesStream(ElToroStream):
    """El Toro Order Lines stream for listing order lines by organization."""

    name = "order_lines"
    path = "/v1/order-lines"
    primary_keys: t.ClassVar[list[str]] = ["id"]
    replication_key = "update_time"
    parent_stream_type = OrganizationsStream
    
    @override
    @property
    def url_base(self) -> str:
        """Return the API URL root for order lines service (same as organizations/stats/campaigns)."""
        # Order lines are also on the hagrid subdomain
        environment = self.config.get("environment", "production")
        if environment == "development":
            return "https://hagrid.api.dev.eltoro.com"
        else:
            return "https://hagrid.api.eltoro.com"
    
    # Define the schema based on the API response structure
    schema = th.PropertiesList(
        # Core order line fields
        th.Property("id", th.StringType, description="ID of the Order Line"),
        th.Property("name", th.StringType, description="Name of the Order Line"),
        th.Property("ref_id", th.StringType, description="Client reference ID of the Order Line"),
        th.Property("org_id", th.StringType, description="ID of the Organization that this Order Line is associated to"),
        
        # Campaign relationship (for SQL joins)
        th.Property("campaign_id", th.StringType, description="ID of the Campaign that this Order Line is associated to"),
        th.Property("campaign_name", th.StringType, description="Name of the Campaign that this Order Line is associated to"),
        
        # Timing
        th.Property("start_time", th.DateTimeType, description="Time the Order Line will start serving"),
        th.Property("end_time", th.DateTimeType, description="Time the Order Line will stop serving"),
        th.Property("create_time", th.DateTimeType, description="Time the Order Line was created at"),
        th.Property("update_time", th.DateTimeType, description="Time the Order Line was updated at"),
        th.Property("delete_time", th.DateTimeType, description="Time the Order Line was deleted at"),
        th.Property("archive_time", th.DateTimeType, description="The time the OrderLine was archived at"),
        th.Property("first_deploy_time", th.DateTimeType, description="Time the Order Line was first deployed"),
        th.Property("last_deploy_time", th.DateTimeType, description="Time the Order Line was last deployed"),
        th.Property("migrated_at", th.DateTimeType, description="Time the Order Line was migrated"),
        
        # Impressions and serving
        th.Property("impressions", th.IntegerType, description="The amount of impressions the Order Line will serve"),
        th.Property("minimum_impressions", th.IntegerType, description="The minimum impressions of the OrderLine"),
        th.Property("impressions_per_day", th.IntegerType, description="The amount of impressions the Order Line will serve per day"),
        th.Property("free_impressions", th.IntegerType, description="The amount of impressions adops is giving to the orderline for free"),
        
        # URLs and targeting
        th.Property("click_through_url", th.StringType, description="The URL the user will be redirected to if the creative is clicked"),
        th.Property("step_function", th.StringType, description="The name of the step function if deployment_destination is GENERIC"),
        
        # Status and state
        th.Property("status", th.StringType, description="Status of the Order line"),
        th.Property("state", th.StringType, description="State of the Order Line"),
        th.Property("reason", th.StringType, description="Reason the Order Line is/was in ERRORED status"),
        
        # Business logic flags
        th.Property("prepay", th.BooleanType, description="Whether or not the Order Line needs to be paid for before it is deployed"),
        th.Property("political", th.BooleanType, description="Whether or not an Order Line is part of a political campaign"),
        th.Property("locked", th.BooleanType, description="Whether or not this Order Line is locked and cannot be updated"),
        th.Property("paid", th.BooleanType, description="Whether or not the Order Line has been paid for"),
        
        # Enums
        th.Property("template_type", th.StringType, description="Template type"),
        th.Property("deployment_destination", th.StringType, description="The Deployment destination for the Order Line"),
        th.Property("ad_type", th.StringType, description="Ad Type"),
        
        # User IDs
        th.Property("first_deploy_user_id", th.StringType, description="ID of the User that first deployed the Order Line"),
        th.Property("last_deploy_user_id", th.StringType, description="ID of the User that last deployed the Order Line"),
        
        # Job and PO IDs
        th.Property("job_id", th.StringType, description="Job ID"),
        th.Property("po_id", th.StringType, description="PO ID"),
        
        # Complex nested objects (stored as JSON)
        th.Property("political_fields", th.ObjectType(), description="Political fields"),
        th.Property("segment_config", th.ObjectType(), description="Segment configuration"),
        th.Property("cpm_override", th.ObjectType(), description="CPM override configuration"),
        th.Property("campaign", th.ObjectType(), description="Campaign object"),
        th.Property("political_transparency", th.ObjectType(), description="Political transparency information"),
        th.Property("deploy_metadata", th.ObjectType(), description="Deployment metadata"),
        th.Property("cost_range", th.ObjectType(), description="Cost range configuration"),
        th.Property("audit_conditions", th.ObjectType(), description="Audit conditions"),
        th.Property("deployment_destination_configuration", th.ObjectType(), description="Deployment destination configuration"),
        th.Property("highest_cpm_audience", th.ObjectType(), description="Highest CPM audience"),
        th.Property("cpm", th.ObjectType(), description="CPM configuration"),
        th.Property("audience_upcharges", th.ObjectType(), description="Audience upcharges"),
        th.Property("cpms", th.ObjectType(), description="CPMs configuration"),
        th.Property("review", th.ObjectType(), description="Review information"),
        
        # Arrays
        th.Property("data_sources_highest_upcharge", th.ArrayType(th.ObjectType()), description="Data sources highest upcharge"),
        th.Property("creatives", th.ArrayType(th.ObjectType()), description="Creatives associated with the order line"),
        th.Property("audiences", th.ArrayType(th.ObjectType()), description="Audiences associated with the order line"),
        th.Property("notes", th.ArrayType(th.ObjectType()), description="Notes on the order line"),
        
        # Simple fields that might be in nested objects
        th.Property("cpm_key", th.StringType, description="The CPM key of the CPM"),
    ).to_dict()
    
    @property
    def state_partitioning_keys(self) -> list[str] | None:
        """Return state partitioning keys for the stream."""
        return ["org_id"]
    
    @override
    def get_url_params(
        self, context: Context | None, next_page_token: t.Any | None
    ) -> dict[str, t.Any]:
        """Get URL parameters for the order lines request."""
        params = {}
        
        # Add pagination
        if next_page_token:
            params["page_token"] = next_page_token
        
        # Set page size (up to 1000 max)
        params["page_size"] = 1000
        
        # Try to filter by org_id if we have it from context
        if context and "org_id" in context:
            # This might not work if the API doesn't support org_id filtering
            # We'll test this and fall back to client-side filtering if needed
            params["filter"] = f"org_id={context['org_id']}"
        
        return params
    
    @override
    def parse_response(self, response: t.Any, context: Context | None = None) -> t.Iterable[dict]:
        """Parse the order lines response and yield individual records."""
        data = response.json()
        
        # Get org_id from context for filtering
        context_org_id = None
        if context and "org_id" in context:
            context_org_id = context["org_id"]
        
        # Parse order lines
        if "order_lines" in data:
            for order_line in data["order_lines"]:
                # If we have a context org_id, filter order lines to match
                if context_org_id and order_line.get("org_id") != context_org_id:
                    # Skip order lines that don't belong to this org
                    continue
                
                # Extract campaign information for SQL joins
                campaign = order_line.get("campaign", {})
                if isinstance(campaign, dict):
                    order_line["campaign_id"] = campaign.get("id")
                    order_line["campaign_name"] = campaign.get("name")
                
                yield order_line
    
    @override
    def get_next_page_token(
        self, 
        response: t.Any, 
        previous_token: t.Any | None
    ) -> t.Any | None:
        """Extract next page token from response."""
        data = response.json()
        return data.get("next_page_token")


class CreativesStream(ElToroStream):
    """El Toro Creatives stream for listing creatives by organization."""

    name = "creatives"
    path = "/v1/creatives"
    primary_keys: t.ClassVar[list[str]] = ["id"]
    replication_key = "update_time"
    parent_stream_type = OrganizationsStream
    
    @override
    @property
    def url_base(self) -> str:
        """Return the API URL root for creatives service (same as organizations/stats/campaigns/order_lines)."""
        # Creatives are also on the hagrid subdomain
        environment = self.config.get("environment", "production")
        if environment == "development":
            return "https://hagrid.api.dev.eltoro.com"
        else:
            return "https://hagrid.api.eltoro.com"
    
    # Define the schema based on the API response structure
    schema = th.PropertiesList(
        # Core creative fields
        th.Property("id", th.StringType, description="ID of the Creative"),
        th.Property("name", th.StringType, description="The official name of the Creative"),
        th.Property("org_id", th.StringType, description="ID of the org the Creative belongs to"),
        
        # Timestamps
        th.Property("create_time", th.DateTimeType, description="The creation timestamp of the Creative"),
        th.Property("update_time", th.DateTimeType, description="The last update timestamp of the Creative"),
        th.Property("delete_time", th.DateTimeType, description="The deletion timestamp of the Creative"),
        th.Property("archive_time", th.DateTimeType, description="The archival timestamp of the Creative"),
        th.Property("expire_time", th.DateTimeType, description="The expiration timestamp of the Creative"),
        th.Property("purge_time", th.DateTimeType, description="The purge timestamp of the Creative"),
        
        # Status and classification
        th.Property("status", th.StringType, description="Status of the Creative"),
        th.Property("type", th.StringType, description="Type of Creative (banner, video, etc.)"),
        th.Property("ad_type", th.StringType, description="Ad type of Creative (banner, video, native, etc.)"),
        th.Property("audit_status", th.StringType, description="Audit status of the creative"),
        th.Property("category", th.StringType, description="Category of the Creative"),
        
        # Creative properties
        th.Property("height", th.IntegerType, description="Height of the Creative file in pixels"),
        th.Property("width", th.IntegerType, description="Width of the Creative file in pixels"),
        th.Property("ad_tag", th.StringType, description="Ad tag of the Creative"),
        th.Property("folder", th.StringType, description="The folder that the Creative resides in"),
        th.Property("thumbnail", th.StringType, description="Thumbnail for the Creative"),
        th.Property("ott_ready", th.BooleanType, description="Whether a video Creative meets all the OTT Video Specifications"),
        
        # Complex nested objects and arrays
        th.Property("files", th.ArrayType(th.ObjectType(
            th.Property("id", th.StringType, description="ID of the Creative file"),
            th.Property("name", th.StringType, description="The official name of the Creative File"),
            th.Property("creative_id", th.StringType, description="ID of the creative object the file connected to"),
            th.Property("create_time", th.DateTimeType, description="Date and time a Creative File was created at"),
            th.Property("update_time", th.DateTimeType, description="Date and time a Creative File was last updated"),
            th.Property("delete_time", th.DateTimeType, description="Date and time a Creative File was deleted"),
            th.Property("type", th.StringType, description="Type of the creative file"),
            th.Property("sub_type", th.StringType, description="Subtype of the creative file"),
            th.Property("bucket", th.StringType, description="S3 Bucket where the Creative File is stored"),
            th.Property("key", th.StringType, description="S3 Key of the Creative File"),
            th.Property("mime", th.StringType, description="IANA published MIME type"),
            th.Property("size", th.IntegerType, description="The byte size of the creative file"),
            th.Property("height", th.IntegerType, description="Height of the creative file in pixels"),
            th.Property("width", th.IntegerType, description="Width of the creative file in pixels"),
            th.Property("etag", th.StringType, description="eTag of the creative file"),
            th.Property("uri", th.StringType, description="URI that the creative is connected to when serving"),
            th.Property("duration", th.IntegerType, description="The length of videos creatives"),
            th.Property("extension", th.StringType, description="The file extension"),
            th.Property("bitrate", th.IntegerType, description="The bitrate"),
        )), description="Files associated with the Creative"),
        
        th.Property("order_lines", th.ArrayType(th.ObjectType()), description="Order lines associated with the creative"),
        th.Property("native_metadata", th.ObjectType(), description="Native metadata for the creative"),
        th.Property("audits", th.ArrayType(th.ObjectType()), description="Audit information for the creative"),
    ).to_dict()
    
    @property
    def state_partitioning_keys(self) -> list[str] | None:
        """Return state partitioning keys for the stream."""
        return ["org_id"]
    
    @override
    def get_url_params(
        self, context: Context | None, next_page_token: t.Any | None
    ) -> dict[str, t.Any]:
        """Get URL parameters for the creatives request."""
        params = {}
        
        # Add pagination
        if next_page_token:
            params["page_token"] = next_page_token
        
        # Set page size (up to 1000 max)
        params["page_size"] = 1000
        
        # Temporarily remove org_id filter to test if that's causing 503 error
        # if context and "org_id" in context:
        #     params["filter"] = f"org_id={context['org_id']}"
        
        return params
    
    @override
    def parse_response(self, response: t.Any, context: Context | None = None) -> t.Iterable[dict]:
        """Parse the creatives response and yield individual records."""
        data = response.json()
        
        # Get org_id from context for filtering
        context_org_id = None
        if context and "org_id" in context:
            context_org_id = context["org_id"]
        
        # Parse creatives
        if "creatives" in data:
            for creative in data["creatives"]:
                # If we have a context org_id, filter creatives to match
                if context_org_id and creative.get("org_id") != context_org_id:
                    # Skip creatives that don't belong to this org
                    continue
                
                yield creative
    
    @override
    def get_next_page_token(
        self, 
        response: t.Any, 
        previous_token: t.Any | None
    ) -> t.Any | None:
        """Extract next page token from response."""
        data = response.json()
        return data.get("next_page_token")


class StatsStream(ElToroStream):
    """El Toro Statistics stream for campaign performance data."""

    name = "stats"
    primary_keys: t.ClassVar[list[str]] = ["org_id", "date", "creative_id", "order_line_id", "campaign_id"]
    replication_key = "date"
    parent_stream_type = OrganizationsStream
    
    @override
    @property
    def url_base(self) -> str:
        """Return the API URL root for stats service (same as organizations)."""
        # Stats are also on the hagrid subdomain, not platform
        environment = self.config.get("environment", "production")
        if environment == "development":
            return "https://hagrid.api.dev.eltoro.com"
        else:
            # For production, try without the 'dev' part
            return "https://hagrid.api.eltoro.com"
    
    # Define the schema based on the API response structure
    schema = th.PropertiesList(
        # Identification fields
        th.Property("org_id", th.StringType, description="Organization ID"),
        th.Property("date", th.DateType, description="Date of the stats record (extracted from start timestamp for daily reporting)"),
        th.Property("start", th.DateTimeType, description="Beginning of the search time frame"),
        th.Property("end", th.DateTimeType, description="End of the search time frame"),
        
        # Metric fields
        th.Property("clicks", th.IntegerType, description="Total number of clicks across all impressions"),
        th.Property("completions", th.IntegerType, description="Number of video completions for video ads"),
        th.Property("conversions", th.IntegerType, description="Total number of post-view and post-click conversions"),
        th.Property("cost", th.NumberType, description="Total cost/spend amount"),
        th.Property("imps", th.IntegerType, description="Total number of impressions served"),
        th.Property("imps_viewed", th.IntegerType, description="Number of viewable impressions per IAB standards"),
        th.Property("pcts_25", th.IntegerType, description="25% video completion rate"),
        th.Property("pcts_50", th.IntegerType, description="50% video completion rate"),
        th.Property("pcts_75", th.IntegerType, description="75% video completion rate"),
        th.Property("post_click_convs", th.IntegerType, description="Post-click conversions only"),
        th.Property("post_view_convs", th.IntegerType, description="Post-view conversions only"),
        th.Property("starts", th.IntegerType, description="Video start events"),
        th.Property("view_measured_imps", th.IntegerType, description="Impressions measured for viewability"),
        
        # Optional detail fields
        th.Property("campaign_id", th.StringType, description="Campaign ID (when level_of_detail includes campaign_id)"),
        th.Property("order_line_id", th.StringType, description="Order Line ID (when level_of_detail includes order_line_id)"),
        th.Property("creative_id", th.StringType, description="Creative ID (when level_of_detail includes creative_id)"),
        
        # Details metadata fields
        th.Property("details_org_id", th.StringType, description="Organization ID from details section"),
        th.Property("results_count", th.IntegerType, description="Total number of result objects from details"),
        
        # Metadata
        th.Property("timezone", th.StringType, description="Timezone the report is in"),
        th.Property("time_frame", th.StringType, description="Time frame aggregation level"),
    ).to_dict()

    @property
    def state_partitioning_keys(self) -> list[str] | None:
        """Return state partitioning keys for the stream."""
        return ["org_id"]
        
    @override
    def get_url(self, context: Context | None) -> str:
        """Override to construct URL with proper org_id from context."""
        if context and "org_id" in context:
            org_id = context["org_id"]
            return f"{self.url_base}/v1/orgs/{org_id}/stats"
        else:
            # Fallback to config org_id
            org_id = self.config.get("org_id")
            if org_id:
                return f"{self.url_base}/v1/orgs/{org_id}/stats"
            else:
                raise ValueError("org_id is required for stats endpoint")

    def get_path(self, context: Context | None = None) -> str:
        """Return the API path with org_id from context or config."""
        # Get org_id from context (when iterating through orgs) or config
        org_id = None
        if context and "org_id" in context:
            org_id = context["org_id"]
        else:
            org_id = self.config.get("org_id")
            
        if not org_id:
            raise ValueError("org_id is required for stats endpoint - either provide it in config or ensure organizations stream runs first")
            
        return f"/v1/orgs/{org_id}/stats"

    @property
    def path(self) -> str:
        """Return the API path - this will be overridden by get_path."""
        return "/v1/orgs/placeholder/stats"

    @override
    def prepare_request_payload(
        self,
        context: Context | None,
        next_page_token: t.Any | None,
    ) -> dict | None:
        """Prepare the POST request payload for the stats endpoint."""
        # Get lookback window from config (default 14 days)
        lookback_days = self.config.get("lookback_window_days", 14)
        
        # Get the starting timestamp with state management
        start_date = self.get_starting_timestamp(context)
        
        if start_date is None:
            # No previous state - use configured start_date or default to 30 days ago
            if self.config.get("start_date"):
                start_date = self.config["start_date"]
            else:
                start_date = datetime.now() - timedelta(days=30)
        else:
            # Apply lookback window to ensure we don't miss data
            start_date = start_date - timedelta(days=lookback_days)
        
        # For chunked windows, use 7-day chunks [[memory:3081053]]
        end_date = start_date + timedelta(days=7)
        
        # Ensure timezone-aware comparison
        now = datetime.now()
        if hasattr(start_date, 'tzinfo') and start_date.tzinfo is not None:
            # start_date is timezone-aware, make now timezone-aware too
            from datetime import timezone
            now = datetime.now(timezone.utc)
        
        if end_date > now:
            end_date = now

        payload = {
            "start_time": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_time": end_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time_frame": "DAY",  # Default to daily aggregation
            "timezone": "UTC",
            # Include all metrics by default
            "metrics": [
                "clicks", "completions", "conversions", "cost", "imps", 
                "imps_viewed", "pcts_25", "pcts_50", "pcts_75", 
                "post_click_convs", "post_view_convs", "starts", "view_measured_imps"
            ],
            # Add all levels of detail for comprehensive breakdown
            "level_of_detail": ["org_id", "campaign_id", "order_line_id", "creative_id"],
        }

        # Add optional filters if configured
        if self.config.get("campaign_ids"):
            payload["campaign_id"] = self.config["campaign_ids"]
        if self.config.get("creative_ids"):
            payload["creative_id"] = self.config["creative_ids"]
        if self.config.get("order_line_ids"):
            payload["order_line_id"] = self.config["order_line_ids"]

        return payload

    def parse_response(self, response: t.Any, context: Context | None = None) -> t.Iterable[dict]:
        """Parse the stats response and yield individual records."""
        data = response.json()
        
        # Get org_id from context or config
        context_org_id = None
        if context and "org_id" in context:
            context_org_id = context["org_id"]
        else:
            context_org_id = self.config.get("org_id")
        
        
        # Extract details for adding to each record
        details = data.get("details", {})
        ids_data = details.get("ids", {})
        
        
        # Parse the nested results structure
        if "results" in data:
            for result_group in data["results"]:
                if "results" in result_group:
                    results = result_group["results"]
                    
                    # Match each result with its corresponding ID combination
                    for idx, result in enumerate(results):
                        # Start with the base result
                        record = dict(result)
                        
                        # Add org_id from context (this is the actual org we're querying)
                        if context_org_id:
                            record["org_id"] = context_org_id
                        
                        # Add corresponding IDs from details.ids array
                        if isinstance(ids_data, list) and idx < len(ids_data):
                            # Each result corresponds to an ID combination at the same index
                            id_combo = ids_data[idx]
                            if isinstance(id_combo, dict):
                                # Add all IDs from this specific combination
                                if "campaign_id" in id_combo:
                                    record["campaign_id"] = id_combo["campaign_id"]
                                if "order_line_id" in id_combo:
                                    record["order_line_id"] = id_combo["order_line_id"]
                                if "creative_id" in id_combo:
                                    record["creative_id"] = id_combo["creative_id"]
                                if "org_id" in id_combo:
                                    record["details_org_id"] = id_combo["org_id"]
                        
                        # If ids_data is a single dict (fallback for simpler responses)
                        elif isinstance(ids_data, dict):
                            if "campaign_id" in ids_data:
                                record["campaign_id"] = ids_data["campaign_id"]
                            if "order_line_id" in ids_data:
                                record["order_line_id"] = ids_data["order_line_id"]
                            if "creative_id" in ids_data:
                                record["creative_id"] = ids_data["creative_id"]
                            if "org_id" in ids_data:
                                record["details_org_id"] = ids_data["org_id"]
                        
                        # Add other details metadata
                        if "results_count" in details:
                            record["results_count"] = details["results_count"]
                        
                        # Add time_frame from request (always DAY for daily reporting)
                        record["time_frame"] = "DAY"
                        
                        # Extract date from start timestamp for daily reporting
                        if "start" in record and record["start"]:
                            try:
                                # Parse the start timestamp and extract just the date part
                                start_timestamp = record["start"]
                                if isinstance(start_timestamp, str):
                                    # Extract date part (YYYY-MM-DD) from timestamp
                                    record["date"] = start_timestamp.split("T")[0]
                            except Exception:
                                # If parsing fails, leave date as None
                                record["date"] = None
                        
                        yield record

    @override
    def get_starting_timestamp(self, context: Context | None) -> datetime | None:
        """Get the starting timestamp for incremental sync with proper state management."""
        # Get the bookmark from state
        state = self.get_context_state(context)
        bookmark = state.get("replication_key_value")
        
        if bookmark:
            # Parse the bookmark timestamp
            if isinstance(bookmark, str):
                try:
                    return datetime.fromisoformat(bookmark.replace('Z', '+00:00'))
                except ValueError:
                    # Fallback to basic parsing
                    return datetime.strptime(bookmark.replace('Z', ''), '%Y-%m-%dT%H:%M:%S')
            elif isinstance(bookmark, datetime):
                return bookmark
        
        # Fall back to configured start_date
        start_date = self.config.get("start_date")
        if start_date:
            if isinstance(start_date, str):
                try:
                    return datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                except ValueError:
                    return datetime.strptime(start_date.replace('Z', ''), '%Y-%m-%dT%H:%M:%S')
            elif isinstance(start_date, datetime):
                return start_date
        
        return None

    @override
    def get_url_params(
        self,
        context: Context | None,
        next_page_token: t.Any | None,
    ) -> dict[str, t.Any]:
        """Return URL parameters (none needed for POST request)."""
        return {}

    @property
    def rest_method(self) -> str:
        """Return HTTP method for this stream."""
        return "POST"
