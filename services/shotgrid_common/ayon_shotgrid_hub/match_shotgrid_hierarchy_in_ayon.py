import collections

from constants import (
    CUST_FIELD_CODE_ID,
    CUST_FIELD_CODE_SYNC,
    SHOTGRID_ID_ATTRIB,
    SHOTGRID_TYPE_ATTRIB,
)

from utils import get_sg_entities

from nxtools import logging


def match_shotgrid_hierarchy_in_ayon(entity_hub, sg_project, sg_session):
    """Replicate a Shotgrid project into AYON.

    This function creates a "deck" which we keep increasing while traversing
    the Shotgrid project and finding new childrens, this is more efficient than
    creating a dictionary with the whle Shotgrid project structure since we
    `popleft` the elements when procesing them.

    Args:
        entity_hub (ayon_api.entity_hub.EntityHub): The AYON EntityHub.
        sg_project (dict): The Shotgrid project.
        sg_project (shotgun_api3.Shotgun): The Shotgrid session.
    """

    sg_entities_by_id, sg_entities_by_parent_id = get_sg_entities(
        sg_session,
        sg_project,
    )

    sg_entities_deck = collections.deque()

    # Append the project's direct children.
    for sg_project_child in sg_entities_by_parent_id[sg_project["id"]]:
        sg_entities_deck.append((entity_hub.project_entity, sg_project_child))

    sg_project_sync_status = "Synced"

    while sg_entities_deck:
        (ay_parent_entity, sg_entity) = sg_entities_deck.popleft()
        logging.debug(f"Processing {sg_entity})")

        ay_entity = None
        sg_entity_sync_status = "Synced"

        # Traverse the parent's children to see if it already exists in AYON.
        for ay_child in ay_parent_entity.children:
            if ay_child.name == sg_entity["name"]:
                ay_entity = ay_child
                logging.debug(f"Entity {ay_entity.name} exists in Ayon.")

        # If we couldn't find it we create it.
        if ay_entity is None:
            ay_entity = _create_new_entity(
                entity_hub,
                ay_parent_entity,
                sg_entity,
            )

        # Make sure that if the AYON entity has a shotgridId attribute it matches SG.
        logging.debug(f"Updating {ay_entity.name} <{ay_entity.id}>.")
        shotgrid_id_attrib = ay_entity.attribs.get_attribute(
            SHOTGRID_ID_ATTRIB
        ).value

        if not shotgrid_id_attrib:
            ay_entity.attribs.set(
                SHOTGRID_ID_ATTRIB,
                sg_entity[SHOTGRID_ID_ATTRIB]
            )
            ay_entity.attribs.set(
                SHOTGRID_TYPE_ATTRIB,
                sg_entity["type"]
            )
        elif str(shotgrid_id_attrib) != str(sg_entity[SHOTGRID_ID_ATTRIB]):
            logging.error("Wrong Shotgrid ID in ayon record.")
            sg_entity_sync_status = "Failed"
            sg_project_sync_status = "Failed"
            # TODO: How to deal with mismatches?

        # Update SG entity with new created data
        sg_entity[CUST_FIELD_CODE_ID] = ay_entity.id
        sg_entities_by_id[sg_entity[SHOTGRID_ID_ATTRIB]] = sg_entity

        entity_id = sg_entity["name"]

        if sg_entity["type"] != "Folder":
            if (
                sg_entity[CUST_FIELD_CODE_ID] != ay_entity.id
                or sg_entity[CUST_FIELD_CODE_SYNC] != sg_entity_sync_status
            ):
                update_data = {
                    CUST_FIELD_CODE_ID: ay_entity.id,
                    CUST_FIELD_CODE_SYNC: sg_entity[CUST_FIELD_CODE_SYNC]
                }
                sg_session.update(
                    sg_entity["type"],
                    sg_entity[SHOTGRID_ID_ATTRIB],
                    update_data
                )

            # If the entity has children, add it to the deck
            entity_id = sg_entity[SHOTGRID_ID_ATTRIB]

        # If the entity has children, add it to the deck
        for sg_child in sg_entities_by_parent_id.get(
            entity_id, []
        ):
            sg_entities_deck.append((ay_entity, sg_child))

    entity_hub.commit_changes()

    sg_session.update(
        "Project",
        sg_project["id"],
        {
            CUST_FIELD_CODE_ID: entity_hub.project_entity.id,
            CUST_FIELD_CODE_SYNC: sg_project_sync_status
        }
    )

def _create_new_entity(entity_hub, parent_entity, sg_entity):
    """Helper method to create entities in the EntityHub.

    Args:
        parent_entity: Ayon parent entity.
        sg_entity (dict): Shotgrid entity to create.
    """
    if sg_entity["type"].lower() == "task":
        new_entity = entity_hub.add_new_task(
            sg_entity["label"],
            name=sg_entity["name"],
            label=sg_entity["label"],
            entity_id=sg_entity[CUST_FIELD_CODE_ID],
            parent_id=parent_entity.id
        )
    else:
        new_entity = entity_hub.add_new_folder(
            sg_entity["type"],
            name=sg_entity["name"],
            label=sg_entity["label"],
            entity_id=sg_entity[CUST_FIELD_CODE_ID],
            parent_id=parent_entity.id
        )

    logging.debug(f"Created new entity: {new_entity.name} ({new_entity.id})")
    logging.debug(f"Parent is: {parent_entity.name} ({parent_entity.id})")
    return new_entity

