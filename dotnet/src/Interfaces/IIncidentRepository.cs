/// <summary>Provides access to incident data loaded from Data/Incidents.json.</summary>
public interface IIncidentRepository
{
    /// <summary>Returns all available incidents with their audit events and worker logs.</summary>
    IReadOnlyList<Incident> GetIncidents();
}
